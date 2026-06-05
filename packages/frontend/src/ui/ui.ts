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

// Representation chips: [command kind, label].
const REPS: [string, string][] = [
  ["cartoon", "Cartoon"], ["surface", "Surface"], ["sticks", "Sticks"],
  ["ball_and_stick", "Ball+Stick"], ["spheres", "Spheres"], ["lines", "Lines"],
  ["nonbonded", "Nonbonded"], ["dots", "Dots"],
];
// Solid-color swatches: [color name the backend knows, display hex].
const SWATCHES: [string, string][] = [
  ["red", "#ff4d4d"], ["orange", "#ff8a33"], ["yellow", "#ffd633"], ["green", "#4ddd5a"],
  ["cyan", "#4ddddd"], ["blue", "#6a8cff"], ["magenta", "#ff66dd"], ["white", "#ffffff"],
];
const SCHEMES: [string, string][] = [
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

function section(title: string, ...body: Node[]): HTMLElement {
  return el("div", { className: "vm-section" }, [
    el("div", { className: "vm-title" }, [title]),
    ...body,
  ]);
}

/** Builds and updates the framework-free app-shell UI. */
export class UI {
  private readonly objectsEl = el("div", { className: "vm-list" });
  private readonly selectionsEl = el("div", { className: "vm-list" });
  private readonly sequenceEl = el("div", { className: "vm-seq" });
  private readonly logEl = el("div", { className: "vm-log" });
  private readonly statusEl = el("span", { className: "vm-status" });
  private readonly statusDot = el("span", { className: "vm-dot" });
  private readonly statusText = el("span", { textContent: "connecting" });
  private trajEl!: HTMLDivElement;
  private trajSlider!: HTMLInputElement;
  private trajLabel!: HTMLSpanElement;
  private targetChip!: HTMLSpanElement;
  private nStates = 1;
  private playing = false;
  private playTimer: number | null = null;

  // The active selection that Representation/Color controls act on (null = all).
  private target: string | null = null;
  private lastScene: DecodedScene | null = null;
  // Console command history (newest last); historyIdx walks it with ↑/↓.
  private history: string[] = [];
  private historyIdx = 0;

  constructor(private readonly handlers: UIHandlers) {
    document.body.append(
      this.buildHeader(),
      this.buildLeftPanel(),
      this.buildRightPanel(),
      this.buildDock(),
    );
    this.wireDragAndDrop();
  }

  // ---- header ----

  private buildHeader(): HTMLElement {
    this.statusEl.append(this.statusDot, this.statusText);
    const viewBtn = (label: string, glyph: string, onclick: () => void) =>
      el("button", { className: "vm-btn vm-icon-btn", onclick }, [
        el("span", { textContent: glyph }), el("span", { textContent: label }),
      ]);

    let quality = false;
    const qualityBtn = viewBtn("HQ", "◐", () => {
      quality = !quality;
      qualityBtn.classList.toggle("active", quality);
      this.handlers.onQuality(quality);
    });

    return el("div", { className: "vm-header" }, [
      el("div", { className: "vm-brand" }, [
        el("span", { className: "vm-logo" }),
        el("span", { textContent: "VibeMol" }),
        el("small", { textContent: "Phase 2" }),
      ]),
      el("div", { className: "vm-spacer" }),
      this.statusEl,
      viewBtn("Reset", "⟲", this.handlers.onResetView),
      viewBtn("PNG", "⤓", this.handlers.onSnapshot),
      qualityBtn,
    ]);
  }

  // ---- left tools panel ----

  private buildLeftPanel(): HTMLElement {
    const demoBtn = el("button", {
      className: "vm-btn", textContent: "Demo", onclick: this.handlers.onDemo,
    });
    const fetchInput = el("input", { className: "vm-input", placeholder: "PDB id (e.g. 1ubq)" });
    const doFetch = () =>
      fetchInput.value.trim() && this.handlers.onCommand(`fetch ${fetchInput.value.trim()}`);
    fetchInput.addEventListener("keydown", (e) => e.key === "Enter" && doFetch());
    const fetchBtn = el("button", { className: "vm-btn", textContent: "Fetch", onclick: doFetch });

    const structure = section(
      "Structure",
      el("div", { className: "vm-load-row" }, [demoBtn, fetchInput, fetchBtn]),
      el("div", { className: "vm-hint", textContent: "or drag & drop a .pdb / .cif / .sdf / .xyz file" }),
    );

    // "Apply to" target chip — clicking it clears back to the whole structure.
    this.targetChip = el("span", { className: "vm-chip", textContent: "all" });
    this.targetChip.onclick = () => this.setTarget(null);
    const applyBar = el("div", { className: "vm-apply" }, [
      el("span", { className: "vm-apply-label", textContent: "Apply to" }), this.targetChip,
    ]);

    const repGrid = el(
      "div",
      { className: "vm-grid" },
      REPS.map(([kind, label]) =>
        el("button", { className: "vm-btn vm-rep", onclick: () => this.applyRep(kind) }, [
          el("i"), el("span", { textContent: label }),
        ]),
      ),
    );
    const representation = section("Representation", applyBar, repGrid);

    const swatches = el(
      "div",
      { className: "vm-swatches" },
      SWATCHES.map(([name, hex]) => {
        const sw = el("div", { className: "vm-swatch", title: name, onclick: () => this.applyColor(name) });
        sw.style.background = hex;
        return sw;
      }),
    );
    const schemes = el(
      "div",
      { className: "vm-schemes" },
      SCHEMES.map(([scheme, label]) =>
        el("button", { className: "vm-btn", textContent: label, onclick: () => this.applyColor(scheme) }),
      ),
    );
    const color = section("Color", swatches, schemes);

    return el("div", { className: "vm-left vm-card vm-scroll" }, [structure, representation, color]);
  }

  // ---- right data panel ----

  private buildRightPanel(): HTMLElement {
    return el("div", { className: "vm-right vm-card vm-scroll" }, [
      section("Objects", this.objectsEl),
      section("Selections", this.selectionsEl),
      section("Sequence", this.sequenceEl),
    ]);
  }

  // ---- bottom dock (trajectory + console) ----

  private buildDock(): HTMLElement {
    this.trajLabel = el("span", { className: "vm-title", textContent: "1 / 1" });
    this.trajSlider = el("input", { className: "vm-slider", type: "range", min: "1", max: "1", value: "1" });
    this.trajSlider.oninput = () => {
      this.stopPlaying();
      this.handlers.onState(Number(this.trajSlider.value));
    };
    const playBtn = el("button", { className: "vm-play", textContent: "▶" });
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
          this.handlers.onState(next);
        }, 250);
      }
    };
    this.trajEl = el("div", { className: "vm-traj" }, [
      el("span", { className: "vm-title", textContent: "State" }),
      playBtn, this.trajSlider, this.trajLabel,
    ]) as HTMLDivElement;

    const input = el("input", {
      className: "vm-console-input",
      placeholder: "command…  (e.g. show sticks, chain A · color spectrum · distance index 1, index 4)",
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && input.value.trim()) {
        const cmd = input.value.trim();
        this.handlers.onCommand(cmd);
        if (this.history[this.history.length - 1] !== cmd) this.history.push(cmd);
        this.historyIdx = this.history.length;
        input.value = "";
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (this.historyIdx > 0) {
          this.historyIdx--;
          input.value = this.history[this.historyIdx];
          input.setSelectionRange(input.value.length, input.value.length);
        }
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        if (this.historyIdx < this.history.length - 1) {
          this.historyIdx++;
          input.value = this.history[this.historyIdx];
        } else {
          this.historyIdx = this.history.length;
          input.value = "";
        }
      }
    });
    const consoleRow = el("div", { className: "vm-console-row" }, [
      el("span", { className: "vm-prompt", textContent: "›" }), input,
    ]);

    return el("div", { className: "vm-dock" }, [this.trajEl, this.logEl, consoleRow]);
  }

  // ---- public update API ----

  setStatus(status: ConnectionStatus): void {
    this.statusText.textContent = status;
    this.statusDot.className = "vm-dot" + (status === "open" ? " ok" : status === "error" ? " err" : "");
  }

  renderScene(scene: DecodedScene): void {
    this.lastScene = scene;
    // Clear a stale target if its selection no longer exists.
    if (this.target && !scene.selections.includes(this.target)) this.setTarget(null, false);
    this.nStates = scene.nStates;
    if (scene.nStates > 1) {
      this.trajEl.style.display = "flex";
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
              el("span", { className: "name" }, [
                o.name,
                el("span", { className: "meta", textContent: ` ${o.nAtoms} atoms` }),
              ]),
              el("button", {
                className: "vm-x", textContent: "✕", title: `delete ${o.name}`,
                onclick: () => this.handlers.onCommand(`delete ${o.name}`),
              }),
            ]),
          )
        : [el("div", { className: "vm-empty", textContent: "Load a structure to begin" })]),
    );

    this.renderSelections(scene);
    this.renderSequence(scene);
  }

  // ---- selection management ----

  private targetSuffix(): string {
    return this.target ? `, ${this.target}` : "";
  }

  private applyRep(kind: string): void {
    this.handlers.onCommand(`as ${kind}${this.targetSuffix()}`);
  }

  private applyColor(spec: string): void {
    this.handlers.onCommand(`color ${spec}${this.targetSuffix()}`);
  }

  private setTarget(name: string | null, refresh = true): void {
    this.target = this.target === name ? null : name; // clicking the active one clears it
    this.targetChip.textContent = this.target ?? "all";
    this.targetChip.classList.toggle("set", this.target != null);
    if (refresh && this.lastScene) this.renderSelections(this.lastScene);
  }

  private renderSelections(scene: DecodedScene): void {
    this.selectionsEl.replaceChildren(
      ...(scene.selections.length
        ? scene.selections.map((name) => this.selectionRow(name))
        : [el("div", { className: "vm-empty", textContent: "Pick an atom or run select" })]),
    );
  }

  private selectionRow(name: string): HTMLElement {
    const active = this.target === name;
    const nameEl = el("span", {
      className: "name",
      textContent: name,
      title: "click to target with Representation/Color",
      onclick: () => this.setTarget(name),
    });
    const renameBtn = el("button", {
      className: "vm-x", textContent: "✎", title: "rename",
      onclick: () => this.beginRename(name, nameEl),
    });
    const deleteBtn = el("button", {
      className: "vm-x", textContent: "✕", title: "delete",
      onclick: () => this.handlers.onCommand(`deselect ${name}`),
    });
    return el("div", { className: "vm-row vm-sel" + (active ? " active" : "") }, [
      nameEl, renameBtn, deleteBtn,
    ]);
  }

  private beginRename(oldName: string, nameEl: HTMLElement): void {
    const input = el("input", { className: "vm-rename", value: oldName });
    nameEl.replaceWith(input);
    input.focus();
    input.select();
    let done = false; // Enter, Escape, and blur can all fire — commit at most once.
    const finish = (apply: boolean) => {
      if (done) return;
      done = true;
      const next = input.value.trim();
      if (apply && next && next !== oldName) {
        if (this.target === oldName) this.setTarget(next, false);
        this.handlers.onCommand(`set_name ${oldName}, ${next}`);
      } else if (this.lastScene) {
        this.renderSelections(this.lastScene); // cancel -> restore the row
      }
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      else if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

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
            className: "vm-res", textContent: r.code,
            title: `${obj.name} ${r.resn}${r.resi} (chain ${chain})`,
            onclick: () => this.handlers.onCommand(`select sele, chain ${chain} and resi ${r.resi}`),
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
    this.sequenceEl.replaceChildren(
      ...(rows.length ? rows : [el("div", { className: "vm-empty", textContent: "—" })]),
    );
  }

  renderLog(log: LogLine[]): void {
    this.logEl.replaceChildren(
      ...log.map((line) =>
        el("div", {
          className:
            "vm-log-line" +
            (line.level === "error" ? " err" : line.message.startsWith(">") ? " cmd" : ""),
          textContent: line.message,
        }),
      ),
    );
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  private stopPlaying(): void {
    this.playing = false;
    if (this.playTimer !== null) {
      clearInterval(this.playTimer);
      this.playTimer = null;
    }
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
