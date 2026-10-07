import {
  CaretRight,
  ChatCircleDots,
  Graph,
  MonitorPlay,
  Trash,
  VideoCamera,
} from "@phosphor-icons/react";
import type { StoredConversation } from "../services/conversationHistory";

interface WorkspaceNavigationProps {
  conversations: StoredConversation[];
  activeConversationId: string | null;
  onConversationSelect: (conversation: StoredConversation) => void;
  onConversationDelete: (conversation: StoredConversation) => void;
  onGraph: () => void;
  onInteractive: () => void;
  onVideo: () => void;
}

export function WorkspaceNavigation({
  conversations,
  activeConversationId,
  onConversationSelect,
  onConversationDelete,
  onGraph,
  onInteractive,
  onVideo,
}: WorkspaceNavigationProps) {
  return (
    <aside className="workspace-rail" aria-label="产品导航" data-od-id="primary-navigation">
      <div className="workspace-brand" data-od-id="product-brand">
        <span className="workspace-brand__copy"><strong>疫苗智绘</strong></span>
      </div>

      <nav className="workspace-nav" aria-label="主要功能">
        <button className="workspace-nav__button is-active" type="button" aria-current="page" aria-label="AI 问答">
          <ChatCircleDots weight="duotone" aria-hidden="true" />
          <span>AI 问答</span>
          <CaretRight className="workspace-nav__arrow" weight="bold" aria-hidden="true" />
        </button>
        <button className="workspace-nav__button" data-testid="navigate-graph" type="button" onClick={onGraph}>
          <Graph weight="duotone" aria-hidden="true" />
          <span>知识图谱</span>
          <CaretRight className="workspace-nav__arrow" weight="bold" aria-hidden="true" />
        </button>
        <button className="workspace-nav__button" data-testid="navigate-interactive" type="button" onClick={onInteractive}>
          <MonitorPlay weight="duotone" aria-hidden="true" />
          <span>互动体验</span>
          <CaretRight className="workspace-nav__arrow" weight="bold" aria-hidden="true" />
        </button>
        <button className="workspace-nav__button" data-testid="navigate-video" type="button" onClick={onVideo}>
          <VideoCamera weight="duotone" aria-hidden="true" />
          <span>科普短视频</span>
          <CaretRight className="workspace-nav__arrow" weight="bold" aria-hidden="true" />
        </button>
      </nav>

      <section className="workspace-recent" aria-labelledby="workspace-recent-title">
        <h2 id="workspace-recent-title">最近</h2>
        <div className="workspace-recent__list" data-testid="recent-conversation-list">
          {conversations.length === 0
            ? <p className="workspace-recent__empty">暂无最近对话</p>
            : conversations.map((conversation) => (
              <div
                className={`workspace-recent__item${conversation.id === activeConversationId ? " is-selected" : ""}`}
                key={conversation.id}
              >
                <button
                  className="workspace-recent__select"
                  data-testid={`recent-conversation-${conversation.id}`}
                  type="button"
                  title={conversation.title}
                  aria-current={conversation.id === activeConversationId ? "true" : undefined}
                  onClick={() => onConversationSelect(conversation)}
                >
                  {conversation.title}
                </button>
                <button
                  className="workspace-recent__delete"
                  data-testid={`delete-conversation-${conversation.id}`}
                  type="button"
                  aria-label={`删除对话：${conversation.title}`}
                  title="删除对话"
                  onClick={() => onConversationDelete(conversation)}
                >
                  <Trash weight="bold" aria-hidden="true" />
                </button>
              </div>
            ))}
        </div>
      </section>
    </aside>
  );
}
