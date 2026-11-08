import { Suspense } from "react";
import { ChatView } from "@/components/chat/chat-view";
import { PageFallback } from "@/components/ui/page-fallback";

export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <ChatView />
    </Suspense>
  );
}
