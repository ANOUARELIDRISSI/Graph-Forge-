import { env } from '../config/env';

export class ApiError extends Error { constructor(public status:number, message:string){super(message)} }
export async function api<T>(path:string, init:RequestInit={}, schema?:{parse:(value:unknown)=>T}):Promise<T>{
  const controller=new AbortController(); const timer=window.setTimeout(()=>controller.abort(),env.apiTimeoutMs);
  try { const response=await fetch(`${env.apiUrl}${path}`,{...init,signal:init.signal??controller.signal,headers:{'Content-Type':'application/json',...init.headers}}); if(!response.ok) throw new ApiError(response.status,await response.text()); const value=await response.json(); return schema?schema.parse(value):value as T; } finally { clearTimeout(timer); }
}
