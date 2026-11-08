"use client";

import { configureStore, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { useState, type ReactNode } from "react";
import { Provider, useDispatch, useSelector } from "react-redux";

type UiState = {
  draft: string;
};

const initialState: UiState = { draft: "" };

const slice = createSlice({
  name: "workspace",
  initialState,
  reducers: {
    setDraft(state, action: PayloadAction<string>) {
      state.draft = action.payload;
    },
    clearDraft(state) {
      state.draft = "";
    },
  },
});

export const actions = slice.actions;

function makeStore() {
  return configureStore({ reducer: slice.reducer });
}

type Store = ReturnType<typeof makeStore>;

export const useWorkspace = useSelector.withTypes<ReturnType<Store["getState"]>>();
export const useWorkspaceDispatch = useDispatch.withTypes<Store["dispatch"]>();

export function StoreProvider({ children }: { children: ReactNode }) {
  const [store] = useState(makeStore);
  return <Provider store={store}>{children}</Provider>;
}
