import { get, set } from 'idb-keyval';
export type Message={id:string;role:'user'|'assistant';content:string;sources?:{url:string}[];createdAt:number;status?:'pending'|'done'|'error'};
export type Conversation={id:string;title:string;messages:Message[];createdAt:number;updatedAt:number;pinned?:boolean};
type Storage={version:2;conversations:Conversation[]}; const KEY='graph-rag-chats:v2';
function migrate():Conversation[]{try{const raw=localStorage.getItem('graph-rag-chats');if(!raw)return [];const old=JSON.parse(raw);localStorage.removeItem('graph-rag-chats');return Array.isArray(old)?old:[]}catch{return []}}
export async function loadChats(){try{return (await get<Storage>(KEY))?.conversations??migrate()}catch{return migrate()}}
let timer:number|undefined; export function saveChats(conversations:Conversation[]){window.clearTimeout(timer);timer=window.setTimeout(()=>set(KEY,{version:2,conversations:conversations.slice(-100)} satisfies Storage),300)}
