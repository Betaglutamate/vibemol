import type { ConnectionStatus, LogLine } from "../scene/store";
import type { DecodedScene } from "../protocol/types";

export interface UIHandlers {
  onCommand: (text: string) => void;
  onFile: (file: File) => void;
  onDemo: () => void;
  onResetView: () => void;
  onSnapshot: () => void;
  onQuality: (on: boolean) => void;
  onState: (n: number) => void; // 1-based trajectory frame
}

const REPS: [string, string][] = [
  ["cartoon", "Cartoon"], ["sticks", "Sticks"], ["ball_and_stick", "Ball+Stick"],
  ["spheres", "Spheres"], ["surface", "Surface"], ["lines", "Lines"],
  ["nonbonded", "Nonbonded"], ["dots", "Dots"],
];
const COLORS: [string, string][] = [
  ["byelement", "Element"], ["bychain", "Chain"], ["spectrum", "Spectrum"],
];

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  for (const c of children) node.append(c);
  return node;
}

/** Builds and updates the framework-free overlay UI (toolbar, panels, console). */
export class UI {
  private readonly logEl: HTMLDivElement;
  private readonly objectsEl: HTMLDivElement;
  private readonly selectionsEl: HTMLDivElement;
  private readonly sequenceEl: HTMLDivElement;
  private readonly statusEl: HTMLSpanElement;
  private readonly trajEl: HTMLDivElement;
  private readonly trajSlider: HTMLInputElement;
  private readonly trajLabel: HTMLSpanElement;
  private nStates = 1;
  private playing = false;
  private playTimer: number | null = null;

  constructor(private readonly handlers: UIHandlers) {
    // --- top toolbar ---
    const repButtons = REPS.map(([kind, label]) =>
      el("button", { className: "vm-btn", textContent: label, onclick: () => handlers.onCommand(`as ${kind}`) }),
    );
    const colorButtons = COLORS.map(([scheme, label]) =>
      el("button", { className: "vm-btn", textContent: label, onclick: () => handlers.onCommand(`color ${scheme}`) }),
    );
    const fetchInput = el("input", { className: "vm-input", placeholder: "PDB id", size: 6 });
    const fetchBtn = el("button", {
      className: "vm-btn",
      textContent: "Fetch",
      onclick: () => fetchInput.value.trim() && handlers.onCommand(`fetch ${fetchInput.value.trim()}`),
    });
    const demoBtn = el("button", { className: "vm-btn", textContent: "Demo", onclick: handlers.onDemo });
    const resetBtn = el("button", {
      className: "vm-btn", textContent: "Reset View", onclick: handlers.onResetView,
    });
    const snapBtn = el("button", {
      className: "vm-btn", textContent: "Snapshot", onclick: handlers.onSnapshot,
    });
    let quality = false;
    const qualityBtn = el("button", { className: "vm-btn", textContent: "Quality: off" });
    qualityBtn.onclick = () => {
      quality = !quality;
      qualityBtn.textContent = `Quality: ${quality ? "on" : "off"}`;
      qualityBtn.classList.toggle("vm-active", quality);
      handlers.onQuality(quality);
    };
    const toolbar = el("div", { className: "vm-toolbar" }, [
      el("span", { className: "vm-label", textContent: "Show" }), ...repButtons,
      el("span", { className: "vm-sep" }),
      el("span", { className: "vm-label", textContent: "Color" }), ...colorButtons,
      el("span", { className: "vm-sep" }), demoBtn, fetchInput, fetchBtn,
      el("span", { className: "vm-sep" }), resetBtn, snapBtn, qualityBtn,
    ]);

    // --- right panel (objects + selections) ---
    this.objectsEl = el("div", { className: "vm-list" });
    this.selectionsEl = el("div", { className: "vm-list" });
    const panel = el("div", { className: "vm-panel" }, [
      el("div", { className: "vm-panel-title", textContent: "Objects" }), this.objectsEl,
      el("div", { className: "vm-panel-title", textContent: "Selections" }), this.selectionsEl,
    ]);

    // --- trajectory controls (shown only for multi-state objects) ---
    this.trajLabel = el("span", { className: "vm-label", textContent: "1 / 1" });
    this.trajSlider = el("input", { className: "vm-slider", type: "range", min: "1", max: "1", value: "1" });
    this.trajSlider.oninput = () => {
      this.stopPlaying();
      handlers.onState(Number(this.trajSlider.value));
    };
    const playBtn = el("button", { className: "vm-btn", textContent: "▶" });
    playBtn.onclick = () => {
      if (this.playing) {
        this.stopPlaying();
        playBtn.textContent = "▶";
      } else {
        this.playing = true;
        playBtn.textContent = "⏸";
        this.playTimer = window.setInterval(() => {
          const next = (Number(this.trajSlider.value) % this.nStates) + 1;
          this.trajSlider.value = String(next);
          handlers.onState(next);
        }, 250);
      }
    };
    this.trajEl = el("div", { className: "vm-traj" }, [
      el("span", { className: "vm-label", textContent: "State" }),
      playBtn, this.trajSlider, this.trajLabel,
    ]);
    this.trajEl.style.display = "none";

    // --- sequence viewer (bottom strip above the console) ---
    this.sequenceEl = el("div", { className: "vm-sequence" });

    // --- bottom console ---
    this.logEl = el("div", { className: "vm-log" });
    const input = el("input", { className: "vm-console-input", placeholder: "command… (try: show sticks, elem C)" });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && input.value.trim()) {
        handlers.onCommand(input.value.trim());
        input.value = "";
      }
    });
    const consoleEl = el("div", { className: "vm-console" }, [this.logEl, input]);

    this.statusEl = el("span", { className: "vm-status", textContent: "connecting…" });
    const hud = el("div", { className: "vm-hud" }, [
      el("b", { textContent: "VibeMol" }),
      el("span", { className: "vm-dim", textContent: " — Phase 1" }),
      el("br"), this.statusEl,
    ]);

    document.body.append(toolbar, panel, this.trajEl, this.sequenceEl, consoleEl, hud);
    this.wireDragAndDrop();
  }

  private stopPlaying(): void {
    this.playing = false;
    if (this.playTimer !== null) {
      clearInterval(this.playTimer);
      this.playTimer = null;
    }
  }

  setStatus(status: ConnectionStatus): void {
    this.statusEl.textContent = status;
  }

  renderScene(scene: DecodedScene): void {
    // Trajectory controls: only meaningful when there is more than one state.
    this.nStates = scene.nStates;
    if (scene.nStates > 1) {
      this.trajEl.style.display = "";
      this.trajSlider.max = String(scene.nStates);
      this.trajSlider.value = String(scene.currentState + 1);
      this.trajLabel.textContent = `${scene.currentState + 1} / ${scene.nStates}`;
    } else {
      this.trajEl.style.display = "none";
      this.stopPlaying();
    }

    this.objectsEl.replaceChildren(
      ...(scene.objects.length
        ? scene.objects.map((o) =>
            el("div", { className: "vm-row" }, [
              el("span", { textContent: `${o.name} · ${o.nAtoms} atoms · ${o.activeReps.join(", ") || "hidden"}` }),
              el("button", {
                className: "vm-x",
                textContent: "✕",
                title: `delete ${o.name}`,
                onclick: () => this.handlers.onCommand(`delete ${o.name}`),
              }),
            ]),
          )
        : [el("div", { className: "vm-dim", textContent: "no objects" })]),
    );
    this.selectionsEl.replaceChildren(
      ...(scene.selections.length
        ? scene.selections.map((name) =>
            el("div", { className: "vm-row" }, [
              el("span", { textContent: name }),
              el("button", {
                className: "vm-x",
                textContent: "✕",
                onclick: () => this.handlers.onCommand(`deselect ${name}`),
              }),
            ]),
          )
        : [el("div", { className: "vm-dim", textContent: "none" })]),
    );
    this.renderSequence(scene);
  }

  /** A clickable one-letter sequence per chain; clicking selects that residue. */
  private renderSequence(scene: DecodedScene): void {
    const rows: Node[] = [];
    for (const obj of scene.objects) {
      const byChain = new Map<string, typeof obj.residues>();
      for (const r of obj.residues) {
        if (!byChain.has(r.chain)) byChain.set(r.chain, []);
        byChain.get(r.chain)!.push(r);
      }
      for (const [chain, residues] of byChain) {
        const letters = residues.map((r) =>
          el("span", {
            className: "vm-res",
            textContent: r.code,
            title: `${obj.name} ${r.resn}${r.resi} (chain ${chain})`,
            onclick: () =>
              this.handlers.onCommand(`select sele, chain ${chain} and resi ${r.resi}`),
          }),
        );
        rows.push(
          el("div", { className: "vm-seq-row" }, [
            el("span", { className: "vm-seq-label", textContent: `${obj.name}/${chain}` }),
            ...letters,
          ]),
        );
      }
    }
    this.sequenceEl.replaceChildren(...rows);
  }

  renderLog(log: LogLine[]): void {
    this.logEl.replaceChildren(
      ...log.map((line) =>
        el("div", { className: line.level === "error" ? "vm-log-err" : "vm-log-line", textContent: line.message }),
      ),
    );
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  private wireDragAndDrop(): void {
    window.addEventListener("dragover", (e) => e.preventDefault());
    window.addEventListener("drop", (e) => {
      e.preventDefault();
      const file = e.dataTransfer?.files?.[0];
      if (file) this.handlers.onFile(file);
    });
  }
}
