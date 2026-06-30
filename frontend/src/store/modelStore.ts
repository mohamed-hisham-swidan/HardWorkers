import { create } from "zustand";

interface ModelState {
  selectedModelName: string;
  availableModels: string[];

  setSelectedModel: (name: string) => void;
  setAvailableModels: (names: string[]) => void;
}

export const useModelStore = create<ModelState>((set) => ({
  selectedModelName: "",
  availableModels: [],

  setSelectedModel: (name) => set({ selectedModelName: name }),
  setAvailableModels: (names) =>
    set({
      availableModels: names,
      selectedModelName: (prev) => prev.selectedModelName || names[0] || "",
    }),
}));
