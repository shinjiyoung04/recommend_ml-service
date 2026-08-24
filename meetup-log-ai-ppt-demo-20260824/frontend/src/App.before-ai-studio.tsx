import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import './compact.css'
import './events.css'
import './evidence.css'

type Provider = { provider_id: number; name: string; type: string }
type Preference = { user_id: string; liked_genres: Record<string,number>; disliked_genres: Record<string,number>; liked_topics: Record<string,number>; disliked_topics: Record<string,number>; liked_brands: Record<string,number>; disliked_brands: Record<string,number>; liked_movies: string[]; direct_movies: string[]; seen_movies: string[]; rewatch_allowed_movies: string[]; countries: string[]; max_runtime?: number; hard_exclusions: string[] }
type Analysis = { user_id: string; text: string; target?: string; attitude: string; preference_score: number; confidence: number; corrected_from?: string; note: string }
type Message = { message_id?: number; user_id: 'A'|'B'; text: string; reply_to_message_id?: number }
type Result = { movie: { internal_id: string; title: string; overview: string; release_date?: string; runtime?: number; vote_average: number; poster_path?: string; providers: Provider[]; provider_link?: string }; group_score: number; reasons: string[]; evidence_level: 'LOW'|'MEDIUM'|'HIGH'; member_scores: { user_id: string; score: number; matched: string[]; penalties: string[] }[] }
type RecommendationMeta = { mode: string; modelVersion: string; dataVersion: string; reflectedMembers: Preference[] }

const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'
const recommendationApi = `${apiBase}/api/v1/recommendations`
const roomId = 'chat-test'
const emptyMember = (user_id:string): Preference => ({ user_id, liked_genres:{}, disliked_genres:{}, liked_topics:{}, disliked_topics:{}, liked_brands:{}, disliked_brands:{}, liked_movies:[], direct_movies:[], seen_movies:[], rewatch_allowed_movies:[], countries:[], hard_exclusions:[] })
const labels: Record<string,string> = { flatrate:'구독', free:'무료', ads:'광고', rent:'대여', buy:'구매' }
const attitudeLabels: Record<string,string> = { STRONG_LIKE:'강한 선호', LIKE:'선호', WEAK_LIKE:'약한 선호', NEUTRAL:'중립', UNCERTAIN:'불확실', DISLIKE:'비선호', STRONG_DISLIKE:'강한 비선호', QUESTION:'질문' }

function App() {
  const [speaker, setSpeaker] = useState<'A'|'B'>('A')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [members, setMembers] = useState<Preference[]>([emptyMember('A'), emptyMember('B')])
  const [analyses, setAnalyses] = useState<Analysis[]>([])
  const [results, setResults] = useState<Result[]>([])
  const [excludedMovieIds, setExcludedMovieIds] = useState<string[]>([])
  const [roundId, setRoundId] = useState('')
  const [reactions, setReactions] = useState<Record<string,string>>({})
  const [analysisPage, setAnalysisPage] = useState(0)
  const [replyTo, setReplyTo] = useState<Message|null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [recommendationMeta, setRecommendationMeta] = useState<RecommendationMeta|null>(null)

  function applyRoomData(data: {messages?:Message[]; members:Preference[]; analyses:Analysis[]; recommended_movie_ids?:string[]}) {
    if (data.messages) setMessages(data.messages)
    setMembers(['A','B'].map(id => data.members.find((x:Preference)=>x.user_id===id) ?? emptyMember(id)))
    setAnalyses(data.analyses)
    setAnalysisPage(0)
    if (data.recommended_movie_ids) setExcludedMovieIds(data.recommended_movie_ids)
  }

  useEffect(() => {
    fetch(`${recommendationApi}/chat/rooms/${roomId}`)
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(applyRoomData)
      .catch(() => setError('저장된 채팅을 불러오지 못했습니다.'))
  }, [])

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    if (!input.trim()) return
    const text = input.trim()
    setInput(''); setError('')
    try {
      const response = await fetch(`${recommendationApi}/chat/messages`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ room_id:roomId, user_id:speaker, text, reply_to_message_id:replyTo?.message_id }) })
      if (!response.ok) throw new Error('채팅 분석에 실패했습니다.')
      const data = await response.json()
      applyRoomData(data)
      setReplyTo(null)
    } catch (e) { setError(e instanceof Error ? e.message : '채팅 분석 실패') }
  }

  async function recommend() {
    setLoading(true); setError('')
    try {
      let currentMembers = members
      if (messages.length) {
        const analysisResponse = await fetch(`${recommendationApi}/chat/rooms/${roomId}`)
        if (!analysisResponse.ok) throw new Error('대화 재분석에 실패했습니다.')
        const analysisData = await analysisResponse.json()
        currentMembers = ['A','B'].map(id => analysisData.members.find((x:Preference)=>x.user_id===id) ?? emptyMember(id))
        applyRoomData(analysisData)
      }
      if (roundId && results.length) await sendEvent('REROLL', undefined, undefined, undefined, roundId)
      const nextRoundId = `round-${crypto.randomUUID()}`
      const response = await fetch(`${recommendationApi}/group`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ roomId, roundId:nextRoundId, members:currentMembers, excludedMovieIds, allowedProviderTypes:['flatrate','free','ads','rent','buy'], limit:3, includeUnknownWatchPath:false }) })
      if (!response.ok) throw new Error('추천 서비스를 확인해 주세요.')
      const data = await response.json()
      if (!data.recommendations.length) throw new Error('더 이상 새로운 추천 후보가 없습니다.')
      setResults(data.recommendations)
      setRecommendationMeta({ mode:data.mode, modelVersion:data.model_version, dataVersion:data.data_version, reflectedMembers:currentMembers })
      setRoundId(nextRoundId)
      setReactions({})
      setExcludedMovieIds(previous => [...new Set([...previous, ...data.recommendations.map((x:Result)=>x.movie.internal_id)])])
      await Promise.all(data.recommendations.map((item:Result, index:number) => sendEvent('IMPRESSION', item.movie.internal_id, index+1, data.model_version, nextRoundId)))
    } catch (e) { setError(e instanceof Error ? e.message : '추천 요청 실패') } finally { setLoading(false) }
  }

  async function sendEvent(eventType:string, movieId?:string, rankNo?:number, modelVersion?:string, eventRoundId = roundId, payload:Record<string,unknown> = {}) {
    if (!eventRoundId) return
    const response = await fetch(`${recommendationApi}/events`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      event_id:crypto.randomUUID(), room_id:roomId, round_id:eventRoundId, user_id:speaker,
      movie_id:movieId, rank_no:rankNo, event_type:eventType, model_version:modelVersion??'weighted-hybrid-0.3.0', payload,
      occurred_at:new Date().toISOString()
    }) })
    if (!response.ok) throw new Error('추천 반응 저장에 실패했습니다.')
  }

  async function react(item:Result, index:number, eventType:'LIKE'|'DISLIKE'|'HOLD'|'SELECT') {
    try {
      await sendEvent(eventType, item.movie.internal_id, index+1)
      setReactions(previous=>({...previous,[item.movie.internal_id]:eventType}))
    } catch (e) { setError(e instanceof Error ? e.message : '추천 반응 저장 실패') }
  }

  async function resetChat() {
    if (!window.confirm('현재 채팅, 성향, 추천 이력을 모두 삭제하고 새로 시작할까요?')) return
    setError('')
    try {
      const response = await fetch(`${recommendationApi}/chat/rooms/${roomId}`, { method:'DELETE' })
      if (!response.ok) throw new Error('대화 초기화에 실패했습니다.')
      setMessages([]); setMembers([emptyMember('A'),emptyMember('B')]); setAnalyses([]); setResults([]); setExcludedMovieIds([]); setRoundId(''); setReactions({}); setAnalysisPage(0); setReplyTo(null); setRecommendationMeta(null)
    } catch (e) { setError(e instanceof Error ? e.message : '대화 초기화 실패') }
  }

  return <main>
    <header><div><span className="eyebrow">MEETUPLOG AI TEST</span><h1>A와 B의 대화로<br/>영화를 추천해요</h1><p>오타를 교정하고, 사람별 선호 강도와 유사 영화를 분석합니다. 성향 근거가 부족하면 평점과 인기도를 보조 기준으로 사용합니다.</p></div><button onClick={recommend} disabled={loading}>{loading?'계산 중…':results.length?'다른 영화 다시 추천':'AI 영화 추천'}</button></header>
    {error && <p className="error">{error}</p>}
    <section className="workspace">
      <div className="chat-panel">
        <div className="panel-title"><h2>테스트 채팅</h2><div className="chat-tools"><span>{messages.length}개 메시지</span><button type="button" onClick={resetChat}>대화 초기화</button></div></div>
        <div className="messages">{messages.length===0?<p className="empty">A 또는 B를 선택하고 영화 취향을 말해보세요.<br/>예: “인터스텔러 같은 영화가 좋아”</p>:messages.map((m,i)=><div className={`bubble ${m.user_id}`} key={m.message_id??i}><b>{m.user_id}</b><span>{m.text}<button className="reply-button" type="button" onClick={()=>setReplyTo(m)}>답장</button></span></div>)}</div>
        {replyTo&&<div className="reply-preview"><span>{replyTo.user_id}에게 답장: {replyTo.text}</span><button type="button" onClick={()=>setReplyTo(null)}>취소</button></div>}
        <form onSubmit={sendMessage}><div className="speaker"><button type="button" className={speaker==='A'?'active':''} onClick={()=>setSpeaker('A')}>A</button><button type="button" className={speaker==='B'?'active':''} onClick={()=>setSpeaker('B')}>B</button></div><input value={input} onChange={e=>setInput(e.target.value)} placeholder={`${speaker}의 메시지를 입력하세요`} /><button type="submit">전송</button></form>
      </div>
      <div className="profiles">
        {members.map(member=><div className="profile" key={member.user_id}><h2><span>{member.user_id}</span> 분석된 성향</h2><PreferenceRows member={member}/></div>)}
        {analyses.length>0&&<div className="latest"><h3>전체 문장 분석 · {analyses.length}개</h3>{[...analyses].reverse().slice(analysisPage*6,analysisPage*6+6).map((a,i)=><div className="analysis-row" key={i}><b>{a.user_id} · {a.target??'대상 미확인'}</b><span>{attitudeLabels[a.attitude]??a.attitude} · {a.preference_score>0?'+':''}{a.preference_score} · 신뢰도 {Math.round(a.confidence*100)}%</span>{a.corrected_from&&<small>“{a.corrected_from}” → “{a.target}” 교정</small>}<small>{a.note}</small></div>)}<div className="analysis-pages"><button type="button" disabled={analysisPage===0} onClick={()=>setAnalysisPage(p=>p-1)}>최신</button><span>{analysisPage+1} / {Math.ceil(analyses.length/6)}</span><button type="button" disabled={(analysisPage+1)*6>=analyses.length} onClick={()=>setAnalysisPage(p=>p+1)}>이전</button></div></div>}
      </div>
    </section>
    {results.length>0&&<section className="results"><div className="section-title"><span className="eyebrow">GROUP TOP 3</span><h2>추천 결과</h2></div>{recommendationMeta&&<RecommendationEvidence meta={recommendationMeta}/>} {results.map((item,index)=><article key={item.movie.title}>
      <div className="poster">{item.movie.poster_path?<img src={`https://image.tmdb.org/t/p/w500${item.movie.poster_path}`} alt={`${item.movie.title} 포스터`}/>:<span>#{index+1}</span>}</div>
      <div className="content" onClick={()=>sendEvent('CLICK',item.movie.internal_id,index+1).catch(()=>undefined)}><div className="rank">TOP {index+1} · 그룹 점수 {Math.round(item.group_score*100)}점 <EvidenceBadge level={item.evidence_level}/></div><h2>{item.movie.title}</h2><p className="meta">{item.movie.release_date?.slice(0,4)} · {item.movie.runtime??'—'}분 · ★ {item.movie.vote_average.toFixed(1)}</p><p>{item.movie.overview}</p><h3>추천 근거</h3><ul className="reason-list">{item.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul><h3>구성원 적합도</h3>{item.member_scores.map(x=><div className="member-evidence" key={x.user_id}><div className="member"><b>{x.user_id}</b><div><i style={{width:`${x.score*100}%`}}/></div><strong>{Math.round(x.score*100)}</strong></div>{(x.matched.length>0||x.penalties.length>0)&&<small>{[...x.matched,...x.penalties].join(' · ')}</small>}</div>)}<div className="reaction-buttons"><button className={reactions[item.movie.internal_id]==='LIKE'?'active':''} onClick={e=>{e.stopPropagation();react(item,index,'LIKE')}}>찬성</button><button className={reactions[item.movie.internal_id]==='DISLIKE'?'active':''} onClick={e=>{e.stopPropagation();react(item,index,'DISLIKE')}}>반대</button><button className={reactions[item.movie.internal_id]==='HOLD'?'active':''} onClick={e=>{e.stopPropagation();react(item,index,'HOLD')}}>보류</button><button className={reactions[item.movie.internal_id]==='SELECT'?'selected':''} onClick={e=>{e.stopPropagation();react(item,index,'SELECT')}}>이 영화 확정</button></div><h3>한국 시청 경로</h3>{item.movie.providers.length?<><div className="providers">{item.movie.providers.map(p=><span key={`${p.provider_id}-${p.type}`}>{p.name} · {labels[p.type]??p.type}</span>)}</div>{item.movie.provider_link&&<a className="watch-link" href={item.movie.provider_link} target="_blank" rel="noreferrer" onClick={e=>{e.stopPropagation();sendEvent('PROVIDER_CLICK',item.movie.internal_id,index+1,undefined,roundId,{url:item.movie.provider_link}).catch(()=>undefined)}}>시청 정보 확인하기 ↗</a>}</>:<p className="unknown">시청 경로 확인 안 됨</p>}</div>
    </article>)}</section>}
  </main>
}

const evidenceLabels = { HIGH:'근거 높음', MEDIUM:'근거 보통', LOW:'근거 부족' }
function EvidenceBadge({level}:{level:'LOW'|'MEDIUM'|'HIGH'}) { return <span className={`evidence-badge ${level.toLowerCase()}`}>{evidenceLabels[level]}</span> }

function RecommendationEvidence({meta}:{meta:RecommendationMeta}) {
  const summaries = meta.reflectedMembers.flatMap(member => preferenceSummary(member).map(value=>`${member.user_id} · ${value}`))
  const lowEvidence = meta.mode === 'LOW_EVIDENCE'
  return <div className="recommendation-evidence"><div><span className={`mode-dot ${lowEvidence?'low':'preference'}`}/><b>{lowEvidence?'취향 근거가 부족해 기본 품질을 함께 반영했습니다.':'대화에서 확인된 취향을 중심으로 계산했습니다.'}</b><small>모델 {meta.modelVersion} · 데이터 {meta.dataVersion}</small></div><h3>이번 추천에 반영된 취향</h3>{summaries.length?<div className="evidence-chips">{summaries.map(value=><span key={value}>{value}</span>)}</div>:<p className="empty">확실하게 확인된 취향이 없어 평점과 인기도를 보조 기준으로 사용했습니다.</p>}</div>
}

function preferenceSummary(member:Preference) {
  return [
    ...Object.entries(member.liked_genres).map(([x,v])=>`${x} 선호 +${v}`),
    ...Object.entries(member.disliked_genres).map(([x,v])=>`${x} 비선호 -${v}`),
    ...Object.entries(member.liked_topics).map(([x,v])=>`${x} 소재 +${v}`),
    ...Object.entries(member.disliked_topics).map(([x,v])=>`${x} 소재 -${v}`),
    ...Object.entries(member.liked_brands).map(([x,v])=>`${x} 선호 +${v}`),
    ...Object.entries(member.disliked_brands).map(([x,v])=>`${x} 비선호 -${v}`),
    ...(member.max_runtime?[`${member.max_runtime}분 이하`]:[]),
    ...member.countries.map(x=>x==='KR'?'한국 영화만':`${x} 제작 영화`),
    ...member.hard_exclusions.map(x=>`${x} 제외`)
  ]
}

function PreferenceRows({member}:{member:Preference}) {
  const rows = [
    ['선호 장르', Object.entries(member.liked_genres).map(([x,v])=>`${x} +${v}`).join(', ')],
    ['비선호 장르', Object.entries(member.disliked_genres).map(([x,v])=>`${x} -${v}`).join(', ')],
    ['선호 소재', Object.entries(member.liked_topics).map(([x,v])=>`${x} +${v}`).join(', ')],
    ['선호 브랜드', Object.entries(member.liked_brands).map(([x,v])=>`${x} +${v}`).join(', ')],
    ['비선호 브랜드', Object.entries(member.disliked_brands).map(([x,v])=>`${x} -${v}`).join(', ')],
    ['유사 영화 기준', member.liked_movies.join(', ')], ['직접 후보', member.direct_movies.join(', ')],
    ['재관람 허용', member.rewatch_allowed_movies.join(', ')], ['제작 국가', member.countries.map(x=>x==='KR'?'한국만':x).join(', ')],
    ['상영시간', member.max_runtime?`${member.max_runtime}분 이하`:''], ['강제 제외', member.hard_exclusions.join(', ')]
  ].filter(([,value])=>value)
  return rows.length?<>{rows.map(([label,value])=><div className="pref-row" key={label}><b>{label}</b><span>{value}</span></div>)}</>:<p className="empty">아직 분석된 성향이 없습니다.</p>
}

export default App
