import { Alert } from "antd";

type Props = {
  appliedThreshold: number;
  candidateCount: number;
  eligibleDescription: string;
  retrievalMethod: string;
};

export function CapabilityRecallSummary(props: Props) {
  const degraded = props.retrievalMethod === "bm25_fallback";
  return (
    <Alert
      description={`最低相关度 ${props.appliedThreshold.toFixed(2)}，已返回 ${props.candidateCount} 个候选，${props.eligibleDescription}。`}
      message={`召回方式：${retrievalMethodLabel(props.retrievalMethod)}`}
      showIcon
      type={degraded ? "warning" : "success"}
    />
  );
}

function retrievalMethodLabel(method: string) {
  if (method === "hybrid") return "BM25 + 向量融合";
  if (method === "bm25_fallback") return "BM25（向量召回异常，已降级）";
  return "BM25";
}
