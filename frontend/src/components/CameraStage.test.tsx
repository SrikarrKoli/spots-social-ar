// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { CameraStage } from './CameraStage';
import type { ObjectSummary, Profile, RecognitionResponse, ThreadResponse } from '../types';
vi.mock('../hooks/useTranscribedRecorder',()=>({useTranscribedRecorder:()=>({state:'idle',error:null})}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const object: ObjectSummary={id:'bottle',identity_key:'bottle',identity_kind:'instance',title:'Water bottle',description:null};
const viewer: Profile={id:'maya',display_name:'Vishal',initials:'V',color:'#fff'};
const thread: ThreadResponse={object,posts:[{id:1,object_id:'bottle',author:viewer,body:'Take this on the walk',created_at:new Date().toISOString(),parent_post_id:null,replies:[]}],updated_at:null};
function snapshot(x:number,visible=true):RecognitionResponse {return {status:'ready',source:'camera',message:null,captured_at:null,frame_width:800,frame_height:600,detections:visible?[{identity_key:'bottle',object,confidence:.9,method:'instance-features+optical-flow',tier:'high',corners:[[x-50,200],[x+50,200],[x+50,300],[x-50,300]],center:[x,250],preview:null}]:[]};}
it('moves both the note marker and live card with the object and hides them on loss',()=>{
 vi.stubGlobal('ResizeObserver',class { constructor(private callback:(entries:unknown[])=>void){} observe(){this.callback([{contentRect:{width:800,height:600}}]);} disconnect(){} });
 const props={recognitionError:null,objects:[object],threads:{bottle:thread},selectedObject:object,onSelectObject:vi.fn(),viewer,listening:true,transcriptionConfigured:true,onPosted:vi.fn(),mode:'live' as const,onModeChange:vi.fn(),overlaysVisible:true,demoOpenSignal:0,onAskAssistant:vi.fn()};
 const view=render(<CameraStage {...props} recognition={snapshot(200)}/>);
 expect(screen.getByRole('button',{name:/Water bottle: 1 note. Open/}).style.left).toBe('200px');
 const first=view.container.querySelector<HTMLElement>('.g-card-slot--tracked')!.style.getPropertyValue('--tracked-left');
 view.rerender(<CameraStage {...props} recognition={snapshot(400)}/>);
 expect(screen.getByRole('button',{name:/Water bottle: 1 note. Open/}).style.left).toBe('400px');
 expect(view.container.querySelector<HTMLElement>('.g-card-slot--tracked')!.style.getPropertyValue('--tracked-left')).not.toBe(first);
 view.rerender(<CameraStage {...props} recognition={snapshot(400,false)}/>);
 expect(screen.queryByRole('button',{name:/Water bottle: 1 note. Open/})).toBeNull();
 expect(view.container.querySelector('.g-card-slot--tracked')).toBeNull();
});
