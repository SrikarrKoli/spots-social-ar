// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';
vi.mock('./api', () => ({ api: {
 profiles: vi.fn().mockResolvedValue([{id:'maya',display_name:'Vishal',initials:'V',color:'#fff'}]),
 objects: vi.fn().mockResolvedValue([{id:'demo-menu-chicken-tikka',identity_key:'demo-menu-chicken-tikka',identity_kind:'demo',title:'Chicken Tikka Masala',description:null}]),
 health: vi.fn().mockResolvedValue({camera_status:'ready',transcription_status:'configured',assistant_status:'ready'}),
 recognition: vi.fn().mockResolvedValue({status:'ready',source:'camera',detections:[],frame_width:1280,frame_height:720}),
 thread: vi.fn().mockResolvedValue({object:{id:'demo-menu-chicken-tikka'},posts:[],updated_at:null}),
} }));
vi.mock('./components/AssistantPanel', () => ({ AssistantPanel: ({autoListen,onClose}: {autoListen:boolean;onClose:()=>void}) => <section aria-label="Voice conversation"><span>{autoListen ? 'Listening automatically' : 'Waiting'}</span><button onClick={onClose}>Close voice conversation</button></section> }));
vi.mock('./hooks/useTranscribedRecorder', () => ({useTranscribedRecorder: () => ({state:'idle',error:null})}));
HTMLElement.prototype.scrollTo=vi.fn();
beforeEach(() => {
 window.history.replaceState(null,'','/#instagram');
 vi.stubGlobal('ResizeObserver',class { observe(){} disconnect(){} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('opens Glasses with the backend live stream even after selecting a demo phone card', async () => {
 render(<App/>);
 await waitFor(() => expect(screen.getByRole('button',{name:/View through glasses/})).toBeTruthy());
 fireEvent.click(screen.getByRole('button',{name:/View through glasses/}));
 expect(screen.getByRole('img',{name:'Live Brio camera view'}).getAttribute('src')).toBe('/api/camera/stream');
 expect(screen.queryByRole('img',{name:/menu on a wooden/})).toBeNull();
 expect(screen.queryByRole('button',{name:'Talk to Spots'})).toBeNull();
 expect(screen.queryByRole('button',{name:'Demo options'})).toBeNull();
 expect(screen.queryAllByRole('combobox')).toHaveLength(0);
});
it('the in-lens assistant starts listening with one tap and closes cleanly', async () => {
 render(<App/>);
 fireEvent.click(screen.getByRole('tab',{name:'Glasses'}));
 fireEvent.click(screen.getByRole('button',{name:'Ask Meta AI'}));
 expect(screen.getByText('Listening automatically')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Close voice conversation'}));
 expect(screen.queryByRole('region',{name:'Voice conversation'})).toBeNull();
 expect(screen.getByRole('img',{name:'Live Brio camera view'})).toBeTruthy();
});
