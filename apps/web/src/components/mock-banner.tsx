import { MOCK_NOTICE } from "../lib/mock";
import { isMockMode } from "../lib/api-client";

// Mock 模式横幅：开发用模拟数据必须可见地区分，不能代替真实端到端验收。
export default function MockBanner() {
  if (!isMockMode()) return null;
  return <div className="banner">{MOCK_NOTICE}</div>;
}
