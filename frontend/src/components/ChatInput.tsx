import { ArrowUp, ChatCircleDots, ImageSquare, Microphone } from "@phosphor-icons/react";
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type MutableRefObject, type Ref } from "react";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";

export type ChatMode = "chat" | "illustration";

interface ChatInputProps {
  value: string;
  disabled: boolean;
  mode: ChatMode;
  isImageGenerating?: boolean;
  isCancellingImage?: boolean;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onModeChange: (mode: ChatMode) => void;
  onCancelImage?: () => void;
  inputRef?: Ref<HTMLTextAreaElement>;
  onMeaningfulInteraction?: () => void;
}

export function mergeVoiceText(base: string, speech: string) {
  if (!speech.trim()) return base;
  if (!base) return speech.trimStart();
  return `${base}${speech.trimStart()}`;
}

export function getComposerTextareaMetrics(scrollHeight: number, lineHeight: number, verticalPadding: number) {
  const maxHeight = lineHeight * 4 + verticalPadding;
  return {
    height: Math.min(scrollHeight, maxHeight),
    scrollable: scrollHeight > maxHeight + 1,
  };
}

export function shouldSubmitComposerKey(key: string, shiftKey: boolean, isComposing: boolean) {
  return key === "Enter" && !shiftKey && !isComposing;
}

export function ChatInput({ value, disabled, mode, isImageGenerating = false, isCancellingImage = false, onChange, onSubmit, onModeChange, onCancelImage, inputRef, onMeaningfulInteraction }: ChatInputProps) {
  const {
    transcript,
    interimTranscript,
    finalTranscript,
    listening,
    resetTranscript,
    browserSupportsSpeechRecognition,
    browserSupportsContinuousListening,
    isMicrophoneAvailable,
  } = useSpeechRecognition();
  const voiceBaseTextRef = useRef("");
  const voiceValueRef = useRef(value);
  const voiceSessionRef = useRef(false);
  const submitTimerRef = useRef<number | undefined>(undefined);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [voiceStarting, setVoiceStarting] = useState(false);
  const [voiceStopping, setVoiceStopping] = useState(false);
  const [voiceNotice, setVoiceNotice] = useState("");
  const [permissionWasRequested, setPermissionWasRequested] = useState(false);
  const liveTranscript = transcript || `${finalTranscript}${interimTranscript}`;

  const setTextareaRef = (node: HTMLTextAreaElement | null) => {
    textareaRef.current = node;
    if (typeof inputRef === "function") inputRef(node);
    else if (inputRef) (inputRef as MutableRefObject<HTMLTextAreaElement | null>).current = node;
  };

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const styles = window.getComputedStyle(textarea);
    const lineHeight = Number.parseFloat(styles.lineHeight) || 21;
    const verticalPadding = (Number.parseFloat(styles.paddingTop) || 0) + (Number.parseFloat(styles.paddingBottom) || 0);
    const metrics = getComposerTextareaMetrics(textarea.scrollHeight, lineHeight, verticalPadding);
    textarea.style.height = `${metrics.height}px`;
    textarea.style.overflowY = metrics.scrollable ? "auto" : "hidden";
  }, [value]);

  useEffect(() => {
    if (!voiceSessionRef.current) return;
    const nextValue = mergeVoiceText(voiceBaseTextRef.current, liveTranscript);
    voiceValueRef.current = nextValue;
    onMeaningfulInteraction?.();
    onChange(nextValue);
  }, [liveTranscript, onChange, onMeaningfulInteraction]);

  useEffect(() => {
    if (!listening) voiceValueRef.current = value;
  }, [listening, value]);

  useEffect(() => {
    if (permissionWasRequested && !isMicrophoneAvailable) {
      setVoiceNotice("无法使用麦克风，请在浏览器中允许麦克风权限。");
      voiceSessionRef.current = false;
      setVoiceStarting(false);
      setVoiceStopping(false);
    }
  }, [isMicrophoneAvailable, permissionWasRequested]);

  const resetVoiceSession = () => {
    voiceSessionRef.current = false;
    voiceBaseTextRef.current = "";
    voiceValueRef.current = "";
    resetTranscript();
  };

  useEffect(() => () => {
    window.clearTimeout(submitTimerRef.current);
    void SpeechRecognition.abortListening();
  }, []);

  const stopVoice = async () => {
    if (!listening && !voiceStarting) return;
    setVoiceStopping(true);
    try {
      await SpeechRecognition.stopListening();
    } finally {
      setVoiceStopping(false);
    }
  };

  const startVoice = async () => {
    if (voiceStarting || voiceStopping || !browserSupportsSpeechRecognition || !isMicrophoneAvailable) return;
    voiceBaseTextRef.current = value;
    voiceValueRef.current = value;
    voiceSessionRef.current = true;
    resetTranscript();
    setVoiceNotice("");
    setPermissionWasRequested(true);
    setVoiceStarting(true);
    try {
      await SpeechRecognition.startListening(browserSupportsContinuousListening
        ? { continuous: true, language: "zh-CN" }
        : { language: "zh-CN" });
    } catch {
      voiceSessionRef.current = false;
      setVoiceNotice("无法启动语音输入，请检查麦克风权限后重试。");
    } finally {
      setVoiceStarting(false);
    }
  };

  const handleVoiceToggle = () => {
    if (listening) void stopVoice();
    else void startVoice();
  };

  const submitCurrentValue = () => {
    onSubmit(voiceValueRef.current);
    resetVoiceSession();
  };

  const handleSubmit = () => {
    if (!listening && !voiceStarting) {
      submitCurrentValue();
      return;
    }
    void stopVoice().finally(() => {
      // Let the final recognition result update the controlled input before sending.
      submitTimerRef.current = window.setTimeout(submitCurrentValue, 0);
    });
  };

  const handleModeChange = (nextMode: ChatMode) => {
    if (nextMode !== "chat" && (listening || voiceStarting)) {
      void SpeechRecognition.abortListening();
      resetVoiceSession();
    }
    onModeChange(nextMode);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (shouldSubmitComposerKey(event.key, event.shiftKey, event.nativeEvent.isComposing)) {
      event.preventDefault();
      if (!isImageGenerating) handleSubmit();
    }
  };

  const isIllustrationMode = mode === "illustration";
  const inputLabel = isIllustrationMode ? "请输入图解主题" : "请输入您的问题";
  const inputDisabled = disabled || isImageGenerating;
  const submitDisabled = isImageGenerating ? isCancellingImage || !onCancelImage : disabled || !value.trim();
  const submitState = isImageGenerating ? (isCancellingImage ? "cancelling" : "stop") : "submit";
  const submitLabel = isImageGenerating ? "停止生成图片" : (isIllustrationMode ? "生成图解" : "发送问题");
  const voiceUnavailable = !browserSupportsSpeechRecognition || !isMicrophoneAvailable;
  const voiceDisabled = inputDisabled || isIllustrationMode || voiceUnavailable || voiceStarting || voiceStopping;
  const voiceTitle = !browserSupportsSpeechRecognition
    ? "当前浏览器暂不支持语音输入"
    : !isMicrophoneAvailable
      ? "无法使用麦克风，请在浏览器中允许麦克风权限。"
      : listening ? "停止语音输入" : "开始语音输入";
  const inputPlaceholder = isIllustrationMode
    ? "请描述您想生成的疫苗图解……"
    : (listening || voiceStarting ? "正在聆听……" : "请输入您的问题……");

  return (
    <div className="chat-composer">
      <div className="chat-composer__toolbar">
        <div className="chat-mode-switch" role="group" aria-label="对话模式">
          <button
            type="button"
            className={mode === "chat" ? "is-active" : ""}
            aria-pressed={mode === "chat"}
            onClick={() => handleModeChange("chat")}
          >
            <ChatCircleDots weight="duotone" aria-hidden="true" />
            问答模式
          </button>
          <button
            type="button"
            className={isIllustrationMode ? "is-active" : ""}
            aria-pressed={isIllustrationMode}
            onClick={() => handleModeChange("illustration")}
          >
            <ImageSquare weight="duotone" aria-hidden="true" />
            图解模式
          </button>
        </div>
        {!isIllustrationMode && <span className="chat-composer__status">按 Enter 发送</span>}
      </div>
      <div className="chat-input">
        <label className="sr-only" htmlFor="question-input">{inputLabel}</label>
        <textarea
          ref={setTextareaRef}
          id="question-input"
          value={value}
          disabled={inputDisabled}
          onChange={(event) => {
            voiceValueRef.current = event.target.value;
            onMeaningfulInteraction?.();
            onChange(event.target.value);
          }}
          onKeyDown={handleKeyDown}
          placeholder={inputPlaceholder}
          autoComplete="off"
          rows={1}
        />
        <div className="chat-input__actions">
          {!isIllustrationMode && (
            <div className={`voice-control${listening ? " is-listening" : ""}`}>
              {listening && <><span className="voice-ring voice-ring--outer" aria-hidden="true" /><span className="voice-ring voice-ring--inner" aria-hidden="true" /></>}
              <button
                className="chat-input__voice"
                type="button"
                disabled={voiceDisabled}
                onClick={handleVoiceToggle}
                aria-label={listening ? "停止语音输入" : "开始语音输入"}
                aria-pressed={listening}
                aria-describedby={voiceNotice ? "voice-input-notice" : undefined}
                title={voiceTitle}
              >
                <Microphone weight={listening ? "fill" : "bold"} aria-hidden="true" />
              </button>
            </div>
          )}
          <button className={`chat-input__submit${isImageGenerating ? " chat-input__submit--stop" : ""}`} type="button" disabled={submitDisabled} data-state={submitState} onClick={isImageGenerating ? onCancelImage : handleSubmit} aria-label={submitLabel}>
            {isImageGenerating ? <span className="chat-input__stop-icon" aria-hidden="true" /> : <ArrowUp weight="bold" aria-hidden="true" />}
          </button>
        </div>
      </div>
      {voiceNotice && <p className="voice-input-notice" id="voice-input-notice" role="status">{voiceNotice}</p>}
      <p className="chat-composer__note">本内容仅供科普参考，不能替代专业医疗建议；如有疑问，请咨询医生或接种机构。</p>
    </div>
  );
}
