// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { NoteCard } from './GlassesNote';
import type { ObjectSummary, Profile, ThreadResponse } from '../types';
vi.mock('../hooks/useTranscribedRecorder',()=>({useTranscribedRecorder:()=>({state:'idle',error:null,start:vi.fn(),stop:vi.fn()})}));
afterEach(cleanup);
const object: ObjectSummary={id:'chair',identity_key:'chair',identity_kind:'instance',title:'Brown leather chair',description:null};
const vishal: Profile={id:'maya',display_name:'Vishal',initials:'V',color:'#fff'};
const aneesh: Profile={id:'theo',display_name:'Aneesh',initials:'A',color:'#fff'};
const lina: Profile={id:'lina',display_name:'Lina',initials:'L',color:'#fff'};
const reply=(id:number,author:Profile,body:string,minute:number)=>({id,object_id:'chair',author,body,created_at:`2026-10-25T12:0${minute}:00Z`,parent_post_id:1,replies:[]});
const note={id:1,object_id:'chair',author:vishal,body:'This is a pretty cool chair',created_at:'2026-10-25T12:00:00Z',parent_post_id:null};
const thread: ThreadResponse={object,posts:[{...note,replies:[reply(2,aneesh,'Agreed, it is so comfy',1),reply(3,lina,'Where did you get it?',2)]}],updated_at:null};

it('shows the original note with every reply threaded under it, without opening anything',()=>{
 render(<NoteCard object={object} thread={thread} viewer={vishal} transcriptionConfigured onClose={vi.fn()} onPosted={vi.fn()}/>);
 const conversation=screen.getByLabelText('2 replies');
 expect(screen.getByText('This is a pretty cool chair')).toBeTruthy();
 expect(conversation.textContent).toContain('Agreed, it is so comfy');
 expect(conversation.textContent).toContain('Where did you get it?');
 expect(screen.queryByRole('button',{name:/View 2 replies/})).toBeNull();
});

it('shows a note without replies on its own',()=>{
 const single: ThreadResponse={...thread,posts:[{...note,replies:[]}]};
 render(<NoteCard object={object} thread={single} viewer={aneesh} transcriptionConfigured onClose={vi.fn()} onPosted={vi.fn()}/>);
 expect(screen.getByText('This is a pretty cool chair')).toBeTruthy();
 expect(screen.queryByLabelText(/repl(y|ies)$/)).toBeNull();
});

it("never cuts off the assistant's voice when the note card closes",async()=>{
 const speech=await import('../speech');
 const stop=vi.spyOn(speech,'stopSpeaking');
 const view=render(<NoteCard object={object} thread={thread} viewer={vishal} transcriptionConfigured onClose={vi.fn()} onPosted={vi.fn()} compact/>);
 view.unmount();
 expect(stop).not.toHaveBeenCalled();
 stop.mockRestore();
});
