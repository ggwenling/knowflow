import { Suspense } from "react";
import { BasesView } from "@/components/knowledge/bases-view";
import { PageFallback } from "@/components/ui/page-fallback";

export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <BasesView />
    </Suspense>
  );
}
