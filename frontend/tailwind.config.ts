import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "var(--bg-base)",
        surface: "var(--bg-surface)",
        panel: "var(--bg-panel)",
        inputbg: "var(--bg-input)",
        "user-msg": "var(--bg-user-msg)",
        "ai-msg": "var(--bg-ai-msg)",
        primary: "var(--accent)",
        muted: "var(--text-muted)",
        "muted-2": "var(--text-muted2)",
        success: "var(--success)",
        error: "var(--error)",
        warning: "var(--warning)",
        border: "var(--border)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
    },
  },
  plugins: [],
} satisfies Config;
