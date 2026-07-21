import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { copilotChat, getCopilotStatus } from "../api/endpoints";
import Alert from "../components/Alert";
import type { CopilotToolTrace, CopilotTurn } from "../api/types";

const SUGGESTIONS = [
  "Qual foi o faturamento total por mês?",
  "Quem são os 5 clientes com maior LTV?",
  "Quantos clientes estão no segmento At Risk?",
  "Busque um fone com cancelamento de ruído",
];

interface ChatMessage extends CopilotTurn {
  toolTrace?: CopilotToolTrace[];
  isError?: boolean;
}

function ToolTraceView({ trace }: { trace: CopilotToolTrace[] }) {
  if (trace.length === 0) return null;
  return (
    <details className="copilot-trace">
      <summary className="text-muted" style={{ cursor: "pointer" }}>
        🛠️ {trace.length} chamada(s) de ferramenta — auditar
      </summary>
      {trace.map((t, idx) => (
        <div key={idx} className="copilot-trace-item">
          <p style={{ margin: "8px 0 4px" }}>
            <span className={`badge ${t.is_error ? "fail" : "pass"}`}>{t.tool}</span>
          </p>
          {t.tool === "query_analytics_dw" && typeof t.input.sql === "string" ? (
            <pre className="copilot-sql">{t.input.sql}</pre>
          ) : (
            <pre className="copilot-sql">{JSON.stringify(t.input, null, 2)}</pre>
          )}
        </div>
      ))}
    </details>
  );
}

export default function CopilotPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: status } = useQuery({ queryKey: ["copilot-status"], queryFn: getCopilotStatus, retry: false });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || isThinking) return;

    const history: CopilotTurn[] = messages
      .filter((m) => !m.isError)
      .map(({ role, content }) => ({ role, content }));

    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    setIsThinking(true);
    try {
      const resp = await copilotChat(message, history);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: resp.answer, toolTrace: resp.tool_trace },
      ]);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Erro ao consultar o AI Copilot.";
      setMessages((prev) => [...prev, { role: "assistant", content: detail, isError: true }]);
    } finally {
      setIsThinking(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>🤖 AI Copilot Analítico</h2>
        <p>
          Pergunte em linguagem natural sobre vendas, clientes e produtos. O Copilot orquestra o Claude com
          ferramentas de <strong>text-to-SQL com guardrails</strong> (DuckDB read-only) e <strong>busca semântica
          vetorial</strong> (Qdrant) — cada consulta executada é auditável abaixo da resposta.
        </p>
      </div>

      {status && !status.enabled && (
        <Alert kind="warning">
          ⚠️ O AI Copilot está desabilitado. Defina <code>ANTHROPIC_API_KEY</code> no ambiente do serviço{" "}
          <code>api</code> para ativá-lo.
        </Alert>
      )}
      {status?.enabled && (
        <Alert kind="info">
          🧠 Modelo ativo: <code>{status.model}</code>
        </Alert>
      )}

      <div className="copilot-window card">
        {messages.length === 0 && (
          <p className="text-muted" style={{ textAlign: "center", padding: "24px 0" }}>
            Comece com uma das sugestões abaixo ou faça sua própria pergunta.
          </p>
        )}
        {messages.map((m, idx) => (
          <div key={idx} className={`copilot-msg ${m.role}${m.isError ? " error" : ""}`}>
            <span className="copilot-msg-role">{m.role === "user" ? "Você" : "Copilot"}</span>
            <div className="copilot-msg-body">{m.content}</div>
            {m.toolTrace && <ToolTraceView trace={m.toolTrace} />}
          </div>
        ))}
        {isThinking && (
          <div className="copilot-msg assistant">
            <span className="copilot-msg-role">Copilot</span>
            <div className="copilot-msg-body text-muted">Analisando os dados…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="suggestion-row">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="suggestion-chip" onClick={() => send(s)} disabled={isThinking}>
            {s}
          </button>
        ))}
      </div>

      <form
        className="copilot-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="input"
          style={{ marginBottom: 0, flex: 1 }}
          placeholder="Ex: qual produto teve a maior receita no último mês?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isThinking}
        />
        <button type="submit" className="btn" disabled={isThinking || input.trim().length === 0}>
          Enviar
        </button>
      </form>
    </div>
  );
}
