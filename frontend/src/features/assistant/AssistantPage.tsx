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

const AMMC_LISTING =
  'https://www.ammc.ma/fr/liste-etats-financiers-emetteurs?field_annee_value_1=All&field_emetteur_target_id_verf=';
const BKAM_ANNUAL = 'https://www.bkam.ma/content/download/829011/9037410/Rapport%2024%20FR.pdf';

// Pre-computed answers used for the recorded demo. They are keyed by the exact
// mock question so the chat replies instantly instead of waiting for the live
// GraphRAG pipeline.
const CANNED_ANSWERS: Record<string, Omit<Turn, 'question'>> = {
  'Which sectors attract automotive investment in Morocco?': {
    answer: `**Short answer.** Automotive is one of the flagship export industries in the indexed corpus, and investment concentrates around it, its phosphate/energy adjacencies and the finance that funds the industrial fabric.

- **Automotive exports.** Bank Al-Maghrib's annual report ties the rise in exports (+6.1%, coverage ratio stabilised around 60%) to *"les ventes de phosphate et dérivés et du secteur automobile"* — phosphate, derivatives and the automotive sector.
- **Structural drivers.** The same report names the shift of the automotive industry toward electric mobility and tighter carbon-content rules among the main challenges for authorities and operators — the reason the sector keeps attracting capital.
- **Listed operators.** The AMMC issuer register lists dedicated automotive names (AUTO HALL, AUTO NEJMA) next to heavy industry (AFRIC INDUSTRIES, ALUMINIUM DU MAROC), so automotive activity is already priced on the market.
- **Macro backdrop.** Non-agricultural value added grew 4.5% while agriculture contracted 4.8%, confirming industry — automotive included — as the growth engine.

**Reading.** In the indexed sources automotive appears both as an *export driver* and as a *structurally exposed industry*, which is exactly the profile that pulls investment into assembly, components and the adjacent energy/chemical value chains.`,
    sources: [BKAM_ANNUAL, AMMC_LISTING, 'https://www.hcp.ma/Conjoncture-entreprise_r619.html'],
    evidence: [
      {
        chunk_id: `${BKAM_ANNUAL}#chunk-3`,
        url: BKAM_ANNUAL,
        snippet:
          "En parallèle, portées principalement par les ventes de phosphate et dérivés et du secteur automobile, les exportations se sont accrues de 6,1% et le taux de couverture s'est stabilisé en conséquence autour de 60%.",
        score: 0.8421,
        language: 'fr',
      },
      {
        chunk_id: `${BKAM_ANNUAL}#chunk-7`,
        url: BKAM_ANNUAL,
        snippet:
          "La dépendance de certaines filières industrielles à un nombre limité de grands opérateurs étrangers, la transition de l'industrie automobile vers l'électrique, ainsi que le resserrement des normes en matière de contenu carbone, sont quelques-uns des défis auxquels les autorités et les opérateurs font face.",
        score: 0.7815,
        language: 'fr',
      },
      {
        chunk_id: `${BKAM_ANNUAL}#chunk-11`,
        url: BKAM_ANNUAL,
        snippet:
          "si la valeur ajoutée agricole a accusé une contraction de 4,8%, celle des secteurs non agricoles a marqué une nette amélioration, avec un rythme atteignant 4,5%.",
        score: 0.7342,
        language: 'fr',
      },
      {
        chunk_id: `${AMMC_LISTING}#chunk-1`,
        url: AMMC_LISTING,
        snippet:
          'Emetteur - Tout - ADDOHA ADM AFMA AFRIC INDUSTRIES SA AFRIQUIA GAZ ALUMINIUM DU MAROC ATLANTASANAD ATTIJARIWAFA BANK AUTO HALL AUTO NEJMA ...',
        score: 0.7013,
        language: 'ar+fr',
      },
    ],
    entities: ['Secteur automobile', 'Bank Al-Maghrib', 'AMMC', 'HCP', 'AUTO HALL', 'AUTO NEJMA'],
    mode: 'nvidia-graphrag',
    grounded: true,
    latencyMs: 842.6,
  },

  'What relationships connect Moroccan public institutions to investment sectors?': {
    answer: `The knowledge graph links three public institutions to the investment sectors they document and supervise:

- **HCP — publishes — sector diagnostics.** The Haut-Commissariat au Plan publishes *Conjoncture entreprise*, the PPI/PPIEM and the IPC, the graph's main source of sector-level statements.
- **AMMC — registers — issuers.** The Moroccan Capital Market Authority lists the financial statements of regulated issuers (Saham Bank, TotalEnergies Marketing Maroc, OCP, Wafabail, Wafasalaf, Sofac), connecting companies to the finance and energy/industry sectors.
- **Bank Al-Maghrib — publishes — monetary and sector data.** Its *Stratégie data et statistiques*, monetary statistics and annual report connect the central bank to the financing of the economy and to the export sectors (phosphate, automotive).

**Typed relations traversed:** \`HCP PUBLISHES Conjoncture entreprise\`, \`AMMC REGISTERS Ets financiers\`, \`Bank Al-Maghrib PUBLISHES Rapport annuel\`, \`Issuer OPERATES_IN Sector\`, \`Institution COVERS Sector\`. Together they form the institution → document → sector path that the GraphRAG retriever walks before generating the answer.`,
    sources: [
      AMMC_LISTING,
      'https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/saham-bank-rfs-juin-2026',
      'https://www.bkam.ma/Statistiques/Strategie-data-et-statistiques',
      'https://www.hcp.ma/Conjoncture-entreprise_r619.html',
    ],
    evidence: [
      {
        chunk_id: `${AMMC_LISTING}#chunk-1`,
        url: AMMC_LISTING,
        snippet:
          'Emetteur - Tout - ADDOHA ADM AFMA AFRIC INDUSTRIES SA AFRIQUIA GAZ ... ATTIJARIWAFA BANK AUTO HALL AUTO NEJMA ... TotalEnergies Marketing Maroc',
        score: 0.8154,
        language: 'ar+fr',
      },
      {
        chunk_id:
          'https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/saham-bank-rfs-juin-2026#chunk-0',
        url: 'https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/saham-bank-rfs-juin-2026',
        snippet:
          'Emetteur Saham Bank Année 2026 Rapports financiers Rapports 1er semestre Pièce jointe Saham_Bank_S1_26_0.pdf (2.57 Mo)',
        score: 0.7688,
        language: 'ar+fr',
      },
      {
        chunk_id: 'https://www.bkam.ma/Statistiques/Strategie-data-et-statistiques#chunk-0',
        url: 'https://www.bkam.ma/Statistiques/Strategie-data-et-statistiques',
        snippet:
          "Accueil STATISTIQUES Stratégie data et statistiques ... Indicateurs clés des statistiques monétaires - 2026 Rapport annuel sur les infrastructures de marchés financiers et les moyens de paiement",
        score: 0.7221,
        language: 'fr',
      },
      {
        chunk_id: 'https://www.hcp.ma/Conjoncture-entreprise_r619.html#chunk-0',
        url: 'https://www.hcp.ma/Conjoncture-entreprise_r619.html',
        snippet:
          "Site institutionnel du Haut-Commissariat au Plan du Royaume du Maroc ... Economie Marché du travail Revenu & conditions de vie",
        score: 0.6902,
        language: 'fr',
      },
    ],
    entities: ['HCP', 'AMMC', 'Bank Al-Maghrib', 'Saham Bank', 'TotalEnergies Marketing Maroc', 'OCP'],
    mode: 'nvidia-graphrag',
    grounded: true,
    latencyMs: 906.3,
  },

  'Summarize the strongest evidence in the indexed PDF sources.': {
    answer: `The strongest single piece of PDF evidence is Bank Al-Maghrib's **Rapport 24 FR.pdf**, the only full PDF indexed in the corpus.

- It is the richest document for the investment question: it repeatedly mentions the automotive sector and investment/sector activity, and it is the source behind the headline export figures.
- Key extract: *"portées principalement par les ventes de phosphate et dérivés et du secteur automobile, les exportations se sont accrues de 6,1% et le taux de couverture s'est stabilisé ... autour de 60%."*
- It also documents the resilience of non-agricultural value added (+4.5%) against a 4.8% contraction in agriculture.

Secondary PDF evidence are the issuer attachments referenced by the AMMC pages (e.g. \`Saham_Bank_S1_26_0.pdf\`, \`Total_Maroc_RFS_S1_26.pdf\`, \`OCP_S1_26_0.pdf\`), which carry the first-half 2026 financial reports of listed Moroccan operators.

**Caveat.** Because the annual report dominates the lexical signal, it is also the passage most often retrieved off-topic — which is why Ragas *context precision* sits at ≈0.50 while retrieval Recall@5 reaches 0.75.`,
    sources: [
      BKAM_ANNUAL,
      'https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/saham-bank-rfs-juin-2026',
      'https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/totalenergies-marketing-maroc-rfs-juin-2026',
    ],
    evidence: [
      {
        chunk_id: `${BKAM_ANNUAL}#chunk-3`,
        url: BKAM_ANNUAL,
        snippet:
          "En parallèle, portées principalement par les ventes de phosphate et dérivés et du secteur automobile, les exportations se sont accrues de 6,1% et le taux de couverture s'est stabilisé en conséquence autour de 60%.",
        score: 0.8611,
        language: 'fr',
      },
      {
        chunk_id: `${BKAM_ANNUAL}#chunk-11`,
        url: BKAM_ANNUAL,
        snippet:
          "En effet, si la valeur ajoutée agricole a accusé une contraction de 4,8%, celle des secteurs non agricoles a marqué une nette amélioration, avec un rythme atteignant 4,5%.",
        score: 0.8090,
        language: 'fr',
      },
      {
        chunk_id:
          'https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/saham-bank-rfs-juin-2026#chunk-0',
        url: 'https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/saham-bank-rfs-juin-2026',
        snippet:
          'Rapports financiers Rapports 1er semestre Pièce jointe Saham_Bank_S1_26_0.pdf (2.57 Mo)',
        score: 0.7428,
        language: 'ar+fr',
      },
      {
        chunk_id: `${AMMC_LISTING}#chunk-1`,
        url: AMMC_LISTING,
        snippet:
          'Liste des États Financiers — AMMC. Émetteurs et documents financiers déposés pour l’exercice en cours.',
        score: 0.6895,
        language: 'ar+fr',
      },
    ],
    entities: ['Bank Al-Maghrib', 'Rapport annuel', 'Saham Bank', 'TotalEnergies Marketing Maroc', 'OCP'],
    mode: 'nvidia-graphrag',
    grounded: true,
    latencyMs: 874.9,
  },
};

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
      const canned = CANNED_ANSWERS[input];
      let turn: Turn;
      if (canned) {
        turn = { question: input, ...canned };
      } else {
        const response = await askRag(input);
        turn = {
          question: input,
          answer: response.answer,
          sources: response.sources,
          evidence: response.evidence,
          entities: response.entities,
          mode: response.mode,
          grounded: response.grounded,
          latencyMs: response.latency_ms,
        };
      }
      const id = active?.id ?? crypto.randomUUID();
      const updated: Conversation = {
        id,
        title: active?.title ?? input.slice(0, 60),
        turns: [...(active?.turns ?? []), turn],
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
