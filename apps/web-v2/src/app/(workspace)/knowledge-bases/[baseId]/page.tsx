import { Suspense } from "react";
import { BaseDetailView } from "@/components/knowledge/base-detail-view";
import { PageFallback } from "@/components/ui/page-fallback";

export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <BaseDetailView />
    </Suspense>
  );
}
