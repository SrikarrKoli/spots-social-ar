"""Local structured LLM intent parsing, with source-grounded write arguments."""
from __future__ import annotations
import asyncio
import json
import re
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field
from .assistant import AssistantError


class ParsedIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['chat', 'add_comment', 'name_object', 'describe_object', 'read_comments', 'edit_comment', 'delete_comment', 'undo', 'cancel', 'clarify']
    object_name: str = Field(default='', max_length=80)
    target_object: str = Field(default='', max_length=80)
    comment_spans: list[str] = Field(default_factory=list, max_length=6)
    action_phrase: str = Field(default='', max_length=200)
    selector: Literal['unspecified', 'last', 'all', 'number', 'matching'] = 'unspecified'
    number: int = Field(default=0, ge=0, le=100)
    matching_text: str = Field(default='', max_length=500)
    read_aloud: bool = False
    question: str = Field(default='', max_length=300)


PROMPT = """You interpret a user's latest spoken turn for Spots, a local object-memory app.
Return only the JSON schema. Do not answer the user or claim any action happened.
Interpret intent semantically, including informal speech, false starts and follow-ups.
Object names are noun phrases (Blue water bottle, Jersey), never instructions/comments.
comment_spans are exact copied substrings containing ONLY the intended comment or
replacement, excluding setup chatter, camera questions, polite instructions, and
object naming. Copy words exactly; do not paraphrase, repair brands, or invent text.
Multiple spans may exclude filler between them. Do not infer comments from an image.
object_name is an explicitly requested new name. target_object is an existing saved
name explicitly referred to; empty means the visible object. Do not choose a saved
object merely because it is in context. action_phrase copies the user's instruction.
History and pending state resolve references, never authorize a new action by themselves.
If unclear what to save/change, select clarify and ask ONE short specific question.
When asked to take a note without content, add_comment with no spans asks for content.
If awaiting_note, a plain dictated sentence is add_comment, but questions, thanks,
setup chatter and asking what notes exist are chat/read_comments. Never save those.
If awaiting_description, a plain object description is describe_object (not a comment).
If awaiting_name, extract object_name and add_comment using the held pending_body.
If pending_edit_ids, handle a number as edit_comment, retaining pending_edit_body.
If pending_delete_ids, handle a number as delete_comment. Never confuse edit/delete.
Naming alone is name_object and must not add a comment. Naming + comment is add_comment.
Read existing comments with read_comments; requesting aloud sets read_aloud true.
Edit an existing comment with edit_comment; comment_spans contain replacement only.
Delete only explicitly requested comments; 'all' only if user explicitly says all/every.
Use selector last for 'that note', 'what I just saved', 'my last comment'; number for
ordinal selection; matching for a comment quoted by content. Otherwise unspecified.
Do not guess missing speech. clarification is better than saving the wrong words.
Examples:
'Okay do you see this fridge? It is in my frame' -> chat, no comment_spans.
'Could you jot down on this thing that I bought it yesterday' -> add_comment,
 action_phrase='jot down', comment_spans=['I bought it yesterday'].
'Call it blue water bottle and say it looks nice' -> add_comment,
 object_name='blue water bottle', comment_spans=['it looks nice'].
'No, change what I just said to I bought it last week' -> edit_comment,
 selector='last', comment_spans=['I bought it last week'].
'What did people leave about this before?' -> read_comments, no comment_spans.
'undo' -> undo, action_phrase='undo'.
For ANY explicit action, action_phrase MUST copy its exact instruction words, e.g.
'jot down', 'Call it', 'change', 'Delete', 'undo'. Do not leave it empty.
A selection like 'the second one' uses number=2 and copies pending_edit_body
EXACTLY into comment_spans if editing. Do not substitute another example's body.
Fill every JSON field. Use empty strings/lists/false/0 only for inapplicable fields.
"""


def normalized(text):
    return re.sub(r'\s+', ' ', text.replace('’', "'").replace('“', '"').replace('”', '"')).strip().casefold()


def validate_grounding(intent: ParsedIntent, payload, objects) -> ParsedIntent:
    current = normalized(payload.message)
    pending = payload.awaiting_note or payload.awaiting_name or payload.pending_edit_ids or payload.pending_delete_ids
    if intent.action not in {'add_comment', 'name_object', 'describe_object'}:
        intent.object_name = ''
    if intent.action not in {'add_comment', 'read_comments', 'edit_comment', 'delete_comment'}:
        intent.target_object = ''
    if intent.action not in {'add_comment', 'edit_comment'}:
        intent.comment_spans = []
    if intent.selector != 'matching':
        intent.matching_text = ''
    if payload.pending_edit_ids or payload.pending_delete_ids:
        selection = re.fullmatch(r'(?:the )?(first|second|third|fourth|fifth|\d+)(?: one| comment| note)?[.!?]*', current)
        if selection and intent.action in {'edit_comment', 'delete_comment'}:
            value = selection.group(1)
            intent.selector = 'number'
            intent.number = int(value) if value.isdigit() else {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5}[value]
    if intent.selector != 'number':
        intent.number = 0
    if intent.selector == 'last' and not re.search(r'\b(?:that|last|just|said|previous|latest)\b', current):
        intent.selector = 'unspecified'
    sources = [current, normalized(payload.pending_title), normalized(payload.pending_body), normalized(payload.pending_edit_body)]
    # Prior user text may resolve an explicit save-that reference; never model-generated claims.
    if re.search(r'\b(?:that|previous|last|said|same)\b', current):
        sources += [normalized(item.content) for item in payload.history[-6:] if item.role == 'user']
    def grounded(value):
        return not value or any(normalized(value) in source for source in sources if source)
    if not all(grounded(span) for span in intent.comment_spans) or not grounded(intent.object_name) or not grounded(intent.matching_text):
        raise AssistantError('I could not confidently separate the name from the comment. Please tell me exactly what the comment should say. Nothing was changed.')
    if intent.action == 'add_comment' and intent.target_object:
        # A brand or descriptive noun is not an existing-object target.
        from .note_commands import clean_object_name
        candidate = clean_object_name(intent.target_object)
        named = next((obj.title for obj in objects if normalized(obj.title) == normalized(candidate)), '')
        intent.target_object = named
    if intent.target_object and normalized(intent.target_object) not in current:
        raise AssistantError('Which saved object did you mean? Nothing was changed.')
    if intent.action_phrase and normalized(intent.action_phrase) not in current and not pending:
        raise AssistantError('Please repeat the action you want me to take. Nothing was changed.')
    if intent.action in {'add_comment', 'name_object', 'edit_comment', 'delete_comment', 'undo'} and not pending and not intent.action_phrase:
        raise AssistantError('Do you want me to save, change, or delete a comment? Nothing was changed.')
    if intent.selector == 'number':
        ordinal = re.search(r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+)\b', current)
        value = ordinal.group(1) if ordinal else ''
        numbers = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10}
        expected = int(value) if value.isdigit() else numbers.get(value)
        if expected != intent.number:
            raise AssistantError('Which comment number did you mean? Nothing was changed.')
        if payload.pending_edit_ids and intent.action == 'delete_comment' or payload.pending_delete_ids and intent.action == 'edit_comment':
            raise AssistantError('Did you want to edit or delete that comment? Nothing was changed.')
    if intent.selector == 'all' and intent.action == 'delete_comment' and not re.search(r'\b(?:all|every|each|everything)\b', current):
        intent.selector = 'last' if re.search(r'\b(?:that|last|just)\b', current) else 'unspecified'
    if intent.selector == 'matching' and not intent.matching_text:
        raise AssistantError('Which comment did you mean? Nothing was changed.')
    if intent.action == 'describe_object' and not intent.object_name:
        from .note_commands import clean_object_name
        intent.object_name = clean_object_name(payload.message)
    if intent.action == 'add_comment':
        from .note_commands import COMMAND
        from .noun_phrases import noun_parts
        command = re.search(COMMAND, payload.message, re.I)
        if command:
            suffix = payload.message[command.end():].strip()
            if re.match(r'^(?:about|on|of|for)\s+', suffix, re.I):
                noun, remainder = noun_parts(suffix)
                if noun and not remainder:
                    intent.comment_spans = []
                    intent.object_name = intent.object_name or noun
    if intent.action == 'add_comment' and intent.action_phrase:
        # A bare request to take a note supplies no comment content.
        if any(re.search(r'\b' + re.escape(normalized(intent.action_phrase)) + r'\b', normalized(span)) for span in intent.comment_spans):
            intent.comment_spans = []
    if sum(len(span) for span in intent.comment_spans) > 500:
        raise AssistantError('Please keep the comment under 500 characters. Nothing was changed.')
    if intent.action in {'add_comment', 'name_object'}:
        from .note_commands import is_conversation_turn
        from .memories import is_note_request as explicit_note
        if is_conversation_turn(payload.message) and not explicit_note(payload.message):
            return ParsedIntent(action='chat')
    return intent


class IntentParser:
    def __init__(self, url, model):
        self.url, self.model = url.rstrip('/'), model
        self.lock = asyncio.Lock()

    async def parse(self, payload, objects):
        context = {
            'latest_utterance': payload.message,
            'history': [item.model_dump() for item in payload.history[-6:]],
            'saved_object_names': [obj.title for obj in objects],
            'pending': {key: getattr(payload, key) for key in ('awaiting_note', 'awaiting_name', 'awaiting_description', 'pending_title', 'pending_body', 'pending_edit_ids', 'pending_edit_body', 'pending_delete_ids', 'last_note_id')},
        }
        schema = ParsedIntent.model_json_schema()
        schema['required'] = list(schema['properties'])
        try:
            async with self.lock:
                async with httpx.AsyncClient(timeout=45) as client:
                    result = await client.post(self.url + '/api/chat', json={
                        'model': self.model, 'stream': False, 'think': False,
                        'format': schema,
                        'messages': [{'role': 'system', 'content': PROMPT}, {'role': 'user', 'content': json.dumps(context)}],
                        'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 700}, 'keep_alive': '10m',
                    })
                    result.raise_for_status()
                intent = ParsedIntent.model_validate_json(result.json()['message']['content'])
            return validate_grounding(intent, payload, objects)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise AssistantError('I could not reliably understand that request. Please repeat it. Nothing was changed.') from error
