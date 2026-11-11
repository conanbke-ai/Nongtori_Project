// 합성 client-only Dashboard 수용 fixture입니다. 격리 제품 컴포넌트를 그대로 실행합니다.
import React, {useEffect} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {FarmerDashboard} from '../../app/components/FarmerDashboard';
type Call={id:number;url:string;method:string;body:unknown;headers:Record<string,string>;settled:boolean;resolve?:(r:Response)=>void};
const calls:Call[]=[],unexpected:string[]=[];let root:Root|null=null,mounts=0,unmounts=0;
// 기존 QA 경계를 유지하여 실제 service worker는 등록하지 않습니다.
const serviceWorkerHidden=Reflect.deleteProperty(Navigator.prototype,'serviceWorker');
if(!serviceWorkerHidden||'serviceWorker' in navigator)throw Error('SERVICE_WORKER_FIXTURE_BOUNDARY_UNAVAILABLE');
const immediate=new Map([
  ['/api/farm-chat-messages',{rows:[],unreadCount:0,hasMore:false}],
  ['/api/community-chat-messages',{rows:[],unreadCount:0,hasMore:false}],
  ['/api/notifications',{rows:[],unreadCount:0}],
  ['/api/phone-notifications',{deliveryAvailable:false}],
]);
window.fetch=async(input,init)=>{
  const url=String(input),method=init?.method??'GET',p=new URL(url,location.href);
  const entry:Call={id:calls.length,url,method,body:init?.body?JSON.parse(String(init.body)):null,headers:Object.fromEntries(new Headers(init?.headers)),settled:false};
  if(method!=='GET'){unexpected.push(method+' '+url);throw Error('SYNTHETIC_WRITE_FORBIDDEN');}
  if(p.origin!==location.origin){unexpected.push(method+' '+url);throw Error('SYNTHETIC_EXTERNAL_FETCH_DENIED');}
  if(method==='GET'&&immediate.has(p.pathname)){entry.settled=true;calls.push(entry);return Response.json(immediate.get(p.pathname));}
  if(method==='GET'&&['/api/farmer-dashboard','/api/scouting-locations'].includes(p.pathname))return new Promise<Response>(resolve=>{entry.resolve=resolve;calls.push(entry);});
  unexpected.push(method+' '+url);throw Error('UNREGISTERED_SYNTHETIC_FETCH');
};
function Fixture(){useEffect(()=>{mounts++;return()=>{unmounts++;};},[]);return <FarmerDashboard/>;}
const streams=new Map<number,{response:Response;createdAt:number;cancelled:boolean;cancelReason:string|null;producerClosed:boolean}>();
const qa={
  mount(){if(root)throw Error('ALREADY_MOUNTED');root=createRoot(document.getElementById('root')!);flushSync(()=>root!.render(<Fixture/>));},
  unmount(){if(!root)throw Error('NOT_MOUNTED');root.unmount();root=null;},
  resolve(id:number,status:number,body:unknown){const c=calls[id];if(!c||c.settled||!c.resolve)throw Error('INVALID_SYNTHETIC_REQUEST');c.settled=true;c.resolve(Response.json(body,{status}));},
  streaming403(id:number){const c=calls[id];if(!c||c.settled||!c.resolve)throw Error('INVALID_SYNTHETIC_REQUEST');const state={response:null as unknown as Response,createdAt:performance.now(),cancelled:false,cancelReason:null as string|null,producerClosed:false};const body=new ReadableStream<Uint8Array>({start(){/* 본문은 enqueue/close/error 없이 열어 둡니다. */},cancel(reason){state.cancelled=true;state.cancelReason=String(reason);}});state.response=new Response(body,{status:403,headers:{'content-type':'application/json'}});streams.set(id,state);c.settled=true;c.resolve(state.response);},
  streamSnapshot(){return [...streams].map(([id,s])=>({id,status:s.response.status,bodyUsed:s.response.bodyUsed,locked:s.response.body?.locked,createdAt:s.createdAt,cancelled:s.cancelled,producerClosed:s.producerClosed}));},
  async cleanupStreams(){for(const s of streams.values())if(s.response.body&&!s.response.bodyUsed)await s.response.body.cancel('합성 QA 종료');},
  snapshot(){return {mounts,unmounts,serviceWorkerHidden,unexpected:[...unexpected],calls:calls.map(c=>({id:c.id,url:c.url,method:c.method,body:c.body,headers:c.headers,settled:c.settled}))};},
};
Object.assign(window,{qa});
