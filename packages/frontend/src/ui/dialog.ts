import { el } from "./dom";

export interface DialogField {
  name: string;
  label: string;
  placeholder?: string;
  value?: string;
}

/** A small modal prompting for one or more text fields. Resolves null on cancel. */
export function openDialog(
  title: string,
  fields: DialogField[],
  okLabel = "OK",
): Promise<Record<string, string> | null> {
  return new Promise((resolve) => {
    const inputs = fields.map((f) =>
      el("input", { className: "vm-input", placeholder: f.placeholder ?? "", value: f.value ?? "" }),
    );
    const rows = fields.map((f, i) =>
      el("label", { className: "vm-field" }, [
        el("span", { className: "vm-field-label", textContent: f.label }),
        inputs[i],
      ]),
    );

    const overlay = el("div", { className: "vm-modal-overlay" });
    const close = (result: Record<string, string> | null) => {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      resolve(result);
    };
    const submit = () => {
      const out: Record<string, string> = {};
      fields.forEach((f, i) => (out[f.name] = inputs[i].value.trim()));
      close(out);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(null);
      else if (e.key === "Enter") submit();
    };
    document.addEventListener("keydown", onKey);

    const modal = el("div", { className: "vm-modal" }, [
      el("div", { className: "vm-modal-title", textContent: title }),
      ...rows,
      el("div", { className: "vm-modal-actions" }, [
        el("button", { className: "vm-btn", textContent: "Cancel", onclick: () => close(null) }),
        el("button", { className: "vm-btn primary", textContent: okLabel, onclick: submit }),
      ]),
    ]);
    overlay.onclick = (e) => e.target === overlay && close(null);
    overlay.append(modal);
    document.body.append(overlay);
    inputs[0]?.focus();
  });
}

/** Prompt for a file via a hidden <input type=file>. Resolves null if cancelled. */
export function pickFile(accept: string): Promise<File | null> {
  return new Promise((resolve) => {
    const input = el("input", { type: "file", accept });
    input.style.display = "none";
    input.onchange = () => {
      resolve(input.files?.[0] ?? null);
      input.remove();
    };
    document.body.append(input);
    input.click();
  });
}
