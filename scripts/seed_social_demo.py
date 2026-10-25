"""Add clearly labelled mock social conversations to locally enrolled objects.

Idempotent; preserves existing comments and edits. Does not create real accounts
or send invitations. Run: uv run python -m scripts.seed_social_demo
"""
from datetime import UTC, datetime
from backend.app.config import Settings
from backend.app.database import Database, seed_demo

# Each tuple is a mock Pravan invitation, another profile's root comment,
# and a reply from the third profile. No inferred facts about the object.
COMMENTS = {
    'black water bottle': (
        'Anyone up for a walk after lunch? I will bring this bottle.',
        'I could use a screen break. Does anyone know a good walking route?',
        'A short walk together sounds good. Let us pick a route.'),
    'blue water bottle': (
        'Trying to drink more water during hackathons. Who wants a refill break?',
        'A quick water break is a good excuse to meet the other teams.',
        'Count me in for a refill break after this round.'),
    'dinnie poster': (
        'This poster makes me want to get everyone together for a photo.',
        'What is the story behind this poster? I would love to hear it.',
        'I would join the group photo. Let us get everyone together.'),
    'flag': (
        'What does this flag mean to you? I would like to hear the story.',
        'Flags make interesting conversation starters. What brought this one here?',
        'Let us swap stories about the things we chose to put in this room.'),
    'fridge': (
        'Anyone interested in a shared dinner after the demo?',
        'Cooking together sounds like a nice way to meet people after the event.',
        'Count me in. Let us choose something simple to make together.'),
    'jersey': (
        'Any other sports fans here? This jersey is a great icebreaker.',
        'I would join a game watch with people from the event.',
        'We could pick the next match and watch it together.'),
    'microwave': (
        'Quick meal break while the build runs. Anyone joining?',
        'I have a few easy snack ideas to share with the other teams.',
        'A group snack break sounds good once this build finishes.'),
    'tissue box': (
        'Keeping this nearby for late-night demo prep. How is everyone holding up?',
        'I am ready for a short break and a chat with the other teams.',
        'Let us take five together once the build finishes.'),
}


def seed_social_demo(database):
    seed_demo(database)
    added = 0
    objects = []
    with database.connect() as db:
        rows = db.execute("SELECT id, title FROM objects WHERE identity_kind = 'instance' ORDER BY title").fetchall()
        for index, obj in enumerate(rows):
            title, object_id = obj['title'], obj['id']
            invitation, other, reply = COMMENTS.get(title.casefold(), (
                f'Anyone else interested in this {title.lower()}? I would love to hear your story.',
                'I noticed this too. What made you choose it?',
                'It would be fun to compare notes and get to know the people here.'))
            other_id, reply_id = ('lina', 'theo') if index % 2 else ('theo', 'lina')
            for role, author, text, parent in (
                ('other', other_id, other, None),
                ('pravan', 'pravan', invitation, None),
                ('reply', reply_id, reply, f'demo-social:{object_id}:pravan'),
            ):
                parent_row = db.execute('SELECT id FROM posts WHERE seed_key=?', (parent,)).fetchone() if parent else None
                cursor = db.execute('''INSERT INTO posts(object_id, author_id, body, created_at, parent_post_id, seed_key)
                    VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(seed_key) DO NOTHING''',
                    (object_id, author, '[Demo] ' + text, datetime.now(UTC).isoformat(),
                     parent_row['id'] if parent_row else None, f'demo-social:{object_id}:{role}'))
                added += cursor.rowcount
            objects.append(title)
    return added, objects


if __name__ == '__main__':
    added, objects = seed_social_demo(Database(Settings.from_env().database_path))
    print(f'Added {added} mock comments/replies across {len(objects)} enrolled objects.')
    print('Profiles: Vishal, Pravan, Theo Brooks, Lina Ortiz, Guest.')
    print('Objects: ' + ', '.join(objects))
