import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import { get, set } from 'idb-keyval';
import { askRag } from '../../api/endpoints';
import type { Evidence } from '../../api/schemas';
import { PageHeader } from '../../components/Layout';
import { Badge, EmptyState, Spinner } from '../../components/ui';
import { Icon } from '../../components/Icon';

type Turn = {
  question: string;
  answer: string;
  sources: string[];
  evidence: Evidence[];
  entities: string[];
  mode: string;
  grounded: boolean;
  latencyMs: number;
};
type Conversation = { id: string; title: string; turns: Turn[]; updatedAt: number };

const KEY = 'atlas-conversations-v2';

async function read(): Promise<Conversation[]> {
  try {
    return (await get<Conversation[]>(KEY)) ?? JSON.parse(localStorage.getItem(KEY) ?? '[]');
  } catch {
    try {
      return JSON.parse(localStorage.getItem(KEY) ?? '[]');
    } catch {
      return [];
    }
  }
}

async function write(chats: Conversation[]) {
  try {
    await set(KEY, chats);
  } catch {
    localStorage.setItem(KEY, JSON.stringify(chats));
  }
}

export default function AssistantPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const chatId = location.pathname.split('/')[2];

  const [chats, setChats] = useState<Conversation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mockQuestions = [
    'Which sectors attract automotive investment in Morocco?',
    'What relationships connect Moroccan public institutions to investment sectors?',
    'Summarize the strongest evidence in the indexed PDF sources.',
  ];

  useEffect(() => {
    let active = true;
    read().then((value) => {
      if (active) {
        setChats(value);
        setLoaded(true);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const active = chats.find((chat) => chat.id === chatId);

  async function send() {
    const input = question.trim();
    if (!input || busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await askRag(input);
      const id = active?.id ?? crypto.randomUUID();
      const updated: Conversation = {
        id,
        title: active?.title ?? input.slice(0, 60),
        turns: [
          ...(active?.turns ?? []),
          {
            question: input,
            answer: response.answer,
            sources: response.sources,
            evidence: response.evidence,
            entities: response.entities,
            mode: response.mode,
            grounded: response.grounded,
            latencyMs: response.latency_ms,
          },
        ],
        updatedAt: Date.now(),
      };
      const next = [updated, ...chats.filter((chat) => chat.id !== id)].slice(0, 100);
      await write(next);
      setChats(next);
      setQuestion('');
      navigate(`/assistant/${id}`, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to get an answer');
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    const next = chats.filter((chat) => chat.id !== id);
    await write(next);
    setChats(next);
    if (id === chatId) navigate('/assistant');
  }

  return (
    <>
      <PageHeader
        eyebrow="GraphRAG assistant"
        title="Ask the knowledge graph"
        description="Answers are grounded in retrieved passages and their k-hop subgraph, with citations, evidence scores and latency reported for every turn."
      />

      <div className="assistant-layout">
        <aside className="card conversation-list">
          <Link className="button button--primary new-conversation" to="/assistant">
            <Icon name="plus" size={15} /> New conversation
          </Link>
          <h2>Conversations</h2>
          {chats.length === 0 && <p className="muted">Your conversations appear here.</p>}
          <ul className="conversation-items">
            {chats.map((chat) => (
              <li key={chat.id} className={chat.id === chatId ? 'is-active' : ''}>
                <Link to={`/assistant/${chat.id}`} className="truncate">
                  {chat.title}
                </Link>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Delete ${chat.title}`}
                  onClick={() => remove(chat.id)}
                >
                  <Icon name="close" size={13} />
                </button>
              </li>
            ))}
          </ul>
          <p className="muted stored-note">Stored locally in this browser.</p>
        </aside>

        <section className="card chat-panel">
          <div className="chat-history" role="log" aria-live="polite">
            {!loaded ? (
              <Spinner label="Loading conversations…" />
            ) : chatId && !active ? (
              <EmptyState
                title="Conversation not found"
                description="It may have been deleted."
                icon="assistant"
                action={
                  <Link className="button" to="/assistant">
                    Start a new chat
                  </Link>
                }
              />
            ) : !active ? (
              <EmptyState
                title="Ask about the indexed sources"
                description="e.g. “Which sectors attract automotive investment in Morocco?”"
                icon="assistant"
              />
            ) : (
              active.turns.map((turn, index) => (
                <article className="message-group" key={index}>
                  <div className="user-message">{turn.question}</div>
                  <div className="assistant-message">
                    <div className="assistant-meta">
                      <span className="assistant-label">
                        <Icon name="assistant" size={12} /> GraphRAG
                      </span>
                      <Badge tone={turn.grounded ? 'ok' : 'warn'}>{turn.grounded ? 'grounded' : 'ungrounded'}</Badge>
                      <Badge tone="muted">{turn.mode}</Badge>
                      <span className="muted">{Math.round(turn.latencyMs)} ms</span>
                    </div>

                    <div className="markdown">
                      <ReactMarkdown rehypePlugins={[rehypeSanitize]}>{turn.answer}</ReactMarkdown>
                    </div>

                    {turn.entities.length > 0 && (
                      <div className="chip-row">
                        {turn.entities.map((entity) => (
                          <span className="chip" key={entity}>
                            {entity}
                          </span>
                        ))}
                      </div>
                    )}

                    {turn.evidence.length > 0 && (
                      <details className="evidence">
                        <summary>{turn.evidence.length} evidence passages</summary>
                        <ul>
                          {turn.evidence.map((item) => (
                            <li key={item.chunk_id}>
                              <div className="evidence-head">
                                <span className="mono muted">score {item.score.toFixed(3)}</span>
                                <span className="muted">{item.language}</span>
                              </div>
                              <p className="evidence-snippet">{item.snippet}</p>
                              <a className="citation" href={item.url} target="_blank" rel="noreferrer">
                                <Icon name="external" size={12} />
                                <span className="truncate">{item.url}</span>
                              </a>
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}

                    {turn.sources.filter((url) => /^https?:\/\//i.test(url)).length > 0 && (
                      <div className="citations">
                        {turn.sources
                          .filter((url) => /^https?:\/\//i.test(url))
                          .map((url) => (
                            <a className="citation" href={url} target="_blank" rel="noopener noreferrer" key={url}>
                              <Icon name="external" size={12} />
                              <span className="truncate">{url}</span>
                            </a>
                          ))}
                      </div>
                    )}
                  </div>
                </article>
              ))
            )}
          </div>

          {!active && (
            <div className="mock-question-row" aria-label="Example questions">
              {mockQuestions.map((example) => (
                <button type="button" className="chip" key={example} onClick={() => setQuestion(example)}>
                  {example}
                </button>
              ))}
            </div>
          )}

          {error && (
            <div className="alert" role="alert">
              <Icon name="warning" size={16} />
              <span>{error}</span>
            </div>
          )}

          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <textarea
              aria-label="Your question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              placeholder="Ask about your sources… (Enter to send, Shift+Enter for a new line)"
            />
            <button type="submit" className="button button--primary" disabled={busy || !question.trim()} aria-label="Send">
              <Icon name="send" size={16} />
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
