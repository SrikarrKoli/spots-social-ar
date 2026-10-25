// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MessagesView } from './MessagesView';
import { api } from '../api';
import type { ObjectSummary, Post, Profile } from '../types';
vi.mock('../api', () => ({ api: { createPost: vi.fn().mockResolvedValue({}) } }));
vi.mock('../hooks/useTranscribedRecorder', () => ({ useTranscribedRecorder: () => ({ state:'idle', error:null }) }));
HTMLElement.prototype.scrollTo = vi.fn();
const viewer: Profile = {id:'maya',display_name:'Vishal',initials:'V',color:'#fff'};
const pravan: Profile = {id:'pravan',display_name:'Pravan',initials:'PR',color:'#fff'};
const object: ObjectSummary = {id:'real-fridge',identity_key:'real-fridge',identity_kind:'instance',title:'Fridge',description:null};
const posts: Post[] = [
 {id:1,object_id:object.id,author:pravan,body:'Dinner after the demo?',created_at:'2026-10-25T08:00:00Z',parent_post_id:null,replies:[]},
 {id:2,object_id:object.id,author:viewer,body:'Bring vegetables',created_at:'2026-10-25T09:00:00Z',parent_post_id:null,replies:[]},
];
afterEach(() => { cleanup(); vi.clearAllMocks(); });
function setup() { const onPosted=vi.fn(); render(<MessagesView profile={viewer} profiles={[viewer,pravan]} onSwitchProfile={vi.fn()} objects={[object]} threads={{[object.id]:{object,posts,updated_at:null}}} selectedObject={object} transcriptionConfigured={true} onOpenLens={vi.fn()} onPosted={onPosted}/>); return onPosted; }
it('shows every saved root comment and uses the real reference image for real objects', () => {
 setup();
 expect(screen.getAllByText('Bring vegetables').length).toBeGreaterThan(0);
 expect(screen.getByText('Saved object memory')).toBeTruthy();
 expect(document.querySelector('.scene-crop')?.getAttribute('style')).toContain('/api/objects/real-fridge/reference');
 expect(screen.queryByText(/group chat created/i)).toBeNull();
});
it('posts Phone comments to the same persistent object API', async () => {
 const onPosted=setup();
 fireEvent.change(screen.getByRole('textbox',{name:'Message'}),{target:{value:'Save this exact comment'}});
 fireEvent.submit(screen.getByRole('textbox',{name:'Message'}).closest('form')!);
 await waitFor(() => expect(api.createPost).toHaveBeenCalledWith('real-fridge',expect.objectContaining({author_id:'maya',body:'Save this exact comment',parent_post_id:null})));
 expect(onPosted).toHaveBeenCalled();
});
