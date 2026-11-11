"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";
import { OnDemand } from "./on-demand";

const Content = dynamic(() => import("./confirm-dialog").then((module) => module.ConfirmDialog), { ssr: false });

export function ConfirmDialog(props: ComponentProps<typeof Content>) {
  return <OnDemand open={props.open}><Content {...props} /></OnDemand>;
}
