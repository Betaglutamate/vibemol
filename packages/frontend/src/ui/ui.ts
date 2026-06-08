import type { ConnectionStatus, LogLine } from "../scene/store";
import type { DecodedScene } from "../protocol/types";
import { el } from "./dom";
import { openDialog, pickFile } from "./dialog";
import { Menubar, type MenuDef, type MenuItem } from "./menubar";

export interface UIHandlers {
  onCommand: (text: string) => void;
  onFile: (file: File) => void; // load a structure file
  onDemo: () => void;
  onResetView: () => void;
  onSnapshot: () => void;
  onQuality: (on: boolean) => void;
  onSpin: (on: boolean) => void;
  onProjection: (orthographic: boolean) => void;
  onState: (n: number) => void; // 1-based trajectory frame
  onSaveSession: () => void;
  onOpenSession: (file: File) => void;
  onExportStructure: () => void;
  onSmiles: (smiles: string, name: string) => void;
  onRunScript: (text: string) => void; // run a multi-line chunk of commands
}

const STARTER_SCRIPT = `# VibeMol script — Cmd/Ctrl+Enter runs the selection or current line.
# Shift+Cmd/Ctrl+Enter (or Run All) runs the whole script.
fetch 1ubq
as cartoon
color spectrum
select site, byres (resn HOH around 4)
show sticks, site
zoom site
`;

const REPS: [string, string][] = [
  ["cartoon", "Cartoon"], ["surface", "Surface"], ["sticks", "Sticks"],
  ["ball_and_stick", "Ball + Stick"], ["spheres", "Spheres"], ["lines", "Lines"],
  ["nonbonded", "Nonbonded"], ["dots", "Dots"],
];
const QUICK_REPS: [string, string][] = [
  ["cartoon", "Cartoon"], ["sticks", "Sticks"], ["surface", "Surface"], ["spheres", "Spheres"],
];
const SWATCHES: [string, string][] = [
  ["red", "#ff4d4d"], ["orange", "#ff8a33"], ["yellow", "#ffd633"], ["green", "#4ddd5a"],
  ["cyan", "#4ddddd"], ["blue", "#6a8cff"], ["magenta", "#ff66dd"], ["white", "#ffffff"],
];
const COLOR_SCHEMES: [string, string][] = [
  ["byelement", "By Element"], ["bychain", "By Chain"], ["spectrum", "Spectrum (B-factor)"],
];
const MEASURE_COUNT: Record<string, number> = { distance: 2, angle: 3, dihedral: 4 };

const FILE_ACCEPT = ".pdb,.ent,.cif,.mmcif,.sdf,.mol,.mol2,.xyz,.smi,.smiles";

/** The app-shell UI: a menu bar + slim quick-access toolbar, right data panel,
 *  and bottom dock (console + trajectory). */
export class UI {
  private readonly objectsEl = el("div", { className: "vm-list" });
  private readonly selectionsEl = el("div", { className: "vm-list" });
  private readonly sequenceEl = el("div", { className: "vm-seq" });
  private readonly logEl = el("div", { className: "vm-log" });
  private readonly statusDot = el("span", { className: "vm-dot" });
  private readonly statusText = el("span", { textContent: "connecting" });
  private readonly hintEl = el("div", { className: "vm-hint-toast" });
  private trajEl!: HTMLDivElement;
  private trajSlider!: HTMLInputElement;
  private trajLabel!: HTMLSpanElement;
  private targetChip!: HTMLSpanElement;
  private scriptPanel!: HTMLElement;
  private scriptArea!: HTMLTextAreaElement;
  private scriptGutter!: HTMLElement;
  private scriptVisible = false;

  private nStates = 1;
  private playing = false;
  private playTimer: number | null = null;
  // View toggles (reflected in the menu checkboxes).
  private quality = false;
  private spin = false;
  private ortho = false;
  // Pick-to-measure state.
  private measureMode: string | null = null;
  private measurePicks: number[] = [];

  private target: string | null = null;
  private lastScene: DecodedScene | null = null;
  // Anchor residue for shift-range selection (set by the last plain/add click).
  private selAnchor: { chain: string; resi: number } | null = null;
  private history: string[] = [];
  private historyIdx = 0;

  constructor(private readonly handlers: UIHandlers) {
    this.hintEl.style.display = "none";
    document.body.append(
      this.buildTopBar(),
      this.buildQuickbar(),
      this.buildRightPanel(),
      this.buildScriptEditor(),
      this.buildDock(),
      this.hintEl,
    );
    this.wireDragAndDrop();
  }

  // ---- top bar (brand + menu bar + status) ----

  private buildTopBar(): HTMLElement {
    const menubar = new Menubar(this.menuDefs());
    const status = el("span", { className: "vm-status" }, [this.statusDot, this.statusText]);
    return el("div", { className: "vm-topbar" }, [
      el("div", { className: "vm-brand" }, [
        el("span", { className: "vm-logo" }), el("span", { textContent: "VibeMol" }),
      ]),
      menubar.element,
      el("div", { className: "vm-spacer" }),
      status,
    ]);
  }

  private menuDefs(): MenuDef[] {
    const repItems: MenuItem[] = REPS.map(([kind, label]) => ({
      kind: "action", label, run: () => this.applyRep(kind),
    }));
    const colorItems: MenuItem[] = [
      ...COLOR_SCHEMES.map(([s, label]): MenuItem => ({
        kind: "action", label, run: () => this.applyColor(s),
      })),
      { kind: "separator" },
      ...SWATCHES.map(([name]): MenuItem => ({
        kind: "action", label: name[0].toUpperCase() + name.slice(1),
        run: () => this.applyColor(name),
      })),
    ];

    return [
      {
        label: "File",
        items: [
          { kind: "action", label: "Open Demo", run: this.handlers.onDemo },
          { kind: "action", label: "Fetch from PDB…", run: () => this.fetchDialog() },
          { kind: "action", label: "From SMILES…", run: () => this.smilesDialog() },
          { kind: "action", label: "Open File…", run: () => this.openFileDialog(FILE_ACCEPT, this.handlers.onFile) },
          { kind: "separator" },
          { kind: "action", label: "Open Session…", run: () => this.openFileDialog(".vibe", this.handlers.onOpenSession) },
          { kind: "action", label: "Save Session", run: this.handlers.onSaveSession },
          { kind: "separator" },
          { kind: "action", label: "Export Image (PNG)", run: this.handlers.onSnapshot },
          { kind: "action", label: "Export Structure (PDB)", run: this.handlers.onExportStructure },
        ],
      },
      {
        label: "View",
        items: [
          { kind: "submenu", label: "Representation", items: repItems },
          { kind: "submenu", label: "Color", items: colorItems },
          { kind: "separator" },
          { kind: "action", label: "Reset View", run: this.handlers.onResetView },
          { kind: "action", label: "Zoom to Selection", run: () => this.handlers.onCommand(`zoom ${this.target ?? "all"}`) },
          {
            kind: "submenu", label: "Background", items: [
              { kind: "action", label: "Dark", run: () => this.handlers.onCommand("bg_color #0b0d10") },
              { kind: "action", label: "White", run: () => this.handlers.onCommand("bg_color white") },
              { kind: "action", label: "Black", run: () => this.handlers.onCommand("bg_color black") },
            ],
          },
          { kind: "separator" },
          { kind: "checkbox", label: "Script Editor", checked: () => this.scriptVisible, toggle: () => this.toggleScript() },
          { kind: "checkbox", label: "Orthographic camera", checked: () => this.ortho, toggle: () => { this.ortho = !this.ortho; this.handlers.onProjection(this.ortho); } },
          { kind: "checkbox", label: "High Quality (SSAO)", checked: () => this.quality, toggle: () => { this.quality = !this.quality; this.handlers.onQuality(this.quality); } },
          { kind: "checkbox", label: "Spin", checked: () => this.spin, toggle: () => { this.spin = !this.spin; this.handlers.onSpin(this.spin); } },
        ],
      },
      {
        label: "Analysis",
        items: [
          { kind: "action", label: "Color by Hydrophobicity", run: () => this.applyColor("hydrophobicity") },
          { kind: "action", label: "Color by Charge", run: () => this.applyColor("charge") },
          { kind: "action", label: "Color by Secondary Structure", run: () => this.applyColor("ss") },
          { kind: "separator" },
          { kind: "action", label: "Hydrophobic Surface", run: () => this.hydrophobicSurface() },
          { kind: "action", label: "Surface Area (SASA)", run: () => this.handlers.onCommand(`sasa ${this.target ?? "all"}`) },
          { kind: "separator" },
          { kind: "action", label: "Polar Contacts (H-bonds)", run: () => this.handlers.onCommand(`polar_contacts ${this.target ?? "all"}`) },
          { kind: "action", label: "Interface Residues…", run: () => this.interfaceDialog() },
          {
            kind: "submenu", label: "Measure", items: [
              { kind: "action", label: "Distance (pick 2)", run: () => this.startMeasure("distance") },
              { kind: "action", label: "Angle (pick 3)", run: () => this.startMeasure("angle") },
              { kind: "action", label: "Dihedral (pick 4)", run: () => this.startMeasure("dihedral") },
            ],
          },
          {
            kind: "submenu", label: "Superpose Objects", items: [
              { kind: "action", label: "Align (sequence-based)…", run: () => this.alignDialog("align", "Align — pair residues by sequence") },
              { kind: "action", label: "Super (structure-based)…", run: () => this.alignDialog("super", "Super — sequence-independent fit") },
              { kind: "action", label: "TM-align / US-align (partial overlap)…", run: () => this.alignDialog("usalign", "TM-align — maximize TM-score") },
            ],
          },
          { kind: "separator" },
          { kind: "action", label: "Clear Measurements", run: () => this.handlers.onCommand("delete_measurements") },
        ],
      },
      {
        label: "Help",
        items: [
          { kind: "action", label: "Console: ↑/↓ for history", run: () => this.toast("Type commands in the console; ↑/↓ recalls history.") },
          { kind: "action", label: "GitHub / Docs", run: () => window.open("https://github.com/Betaglutamate/vibemol", "_blank") },
        ],
      },
    ];
  }

  // ---- quick-access toolbar ----

  private buildQuickbar(): HTMLElement {
    const reps = QUICK_REPS.map(([kind, label]) =>
      el("button", { className: "vm-btn", textContent: label, onclick: () => this.applyRep(kind) }),
    );
    const swatches = SWATCHES.map(([name, hex]) => {
      const sw = el("div", { className: "vm-swatch", title: name, onclick: () => this.applyColor(name) });
      sw.style.background = hex;
      return sw;
    });
    this.targetChip = el("span", { className: "vm-chip", textContent: "all" });
    this.targetChip.onclick = () => this.setTarget(null);

    return el("div", { className: "vm-quickbar vm-card" }, [
      el("span", { className: "vm-q-label", textContent: "Show" }), ...reps,
      el("span", { className: "vm-sep" }),
      el("span", { className: "vm-q-label", textContent: "Color" }), ...swatches,
      el("span", { className: "vm-sep" }),
      el("span", { className: "vm-q-label", textContent: "Apply to" }), this.targetChip,
    ]);
  }

  // ---- dialogs / menu actions ----

  private async fetchDialog(): Promise<void> {
    const v = await openDialog("Fetch from PDB", [{ name: "id", label: "PDB id", placeholder: "1ubq" }], "Fetch");
    if (v?.id) this.handlers.onCommand(`fetch ${v.id}`);
  }

  private async smilesDialog(): Promise<void> {
    const v = await openDialog("Build from SMILES", [
      { name: "smiles", label: "SMILES", placeholder: "CC(=O)Oc1ccccc1C(=O)O" },
      { name: "name", label: "Name", value: "ligand" },
    ], "Build");
    if (v?.smiles) this.handlers.onSmiles(v.smiles, v.name || "ligand");
  }

  private async interfaceDialog(): Promise<void> {
    const v = await openDialog("Interface Residues", [
      { name: "a", label: "Selection 1", placeholder: "chain A", value: "chain A" },
      { name: "b", label: "Selection 2", placeholder: "chain B", value: "chain B" },
      { name: "cutoff", label: "Cutoff (Å)", value: "5" },
    ]);
    if (v?.a && v?.b) this.handlers.onCommand(`interface ${v.a}, ${v.b}, ${v.cutoff || "5"}`);
  }

  private async alignDialog(method: "align" | "super" | "usalign", title: string): Promise<void> {
    const objs = this.lastScene?.objects.map((o) => o.name) ?? [];
    const v = await openDialog(title, [
      { name: "mobile", label: "Mobile object (moved)", value: objs[0] ?? "" },
      { name: "target", label: "Target object (fixed)", value: objs[1] ?? "" },
    ], "Superpose");
    if (v?.mobile && v?.target) this.handlers.onCommand(`${method} ${v.mobile}, ${v.target}`);
  }

  private async openFileDialog(accept: string, onFile: (f: File) => void): Promise<void> {
    const file = await pickFile(accept);
    if (file) onFile(file);
  }

  private hydrophobicSurface(): void {
    this.handlers.onCommand(`color hydrophobicity${this.targetSuffix()}`);
    this.handlers.onCommand(`as surface${this.targetSuffix()}`);
  }

  // ---- pick-to-measure ----

  private startMeasure(kind: string): void {
    this.measureMode = kind;
    this.measurePicks = [];
    this.toast(`${kind[0].toUpperCase() + kind.slice(1)}: click ${MEASURE_COUNT[kind]} atoms (Esc to cancel)`, true);
  }

  /** Called by the app on an atom pick. Measure mode collects atoms; otherwise the
   *  whole residue is selected (modifier keys extend/add — see selectResidue). */
  handlePick(objectName: string, atomIndex: number, mods: { range: boolean; add: boolean }): void {
    if (this.measureMode) {
      this.measurePicks.push(atomIndex + 1); // commands use 1-based index
      const need = MEASURE_COUNT[this.measureMode];
      if (this.measurePicks.length >= need) {
        const sels = this.measurePicks.map((i) => `index ${i}`).join(", ");
        this.handlers.onCommand(`${this.measureMode} ${sels}`);
        this.measureMode = null;
        this.measurePicks = [];
        this.hideToast();
      } else {
        this.toast(`Click ${need - this.measurePicks.length} more atom(s)`, true);
      }
      return;
    }
    const obj = this.lastScene?.objects.find((o) => o.name === objectName);
    if (!obj) return;
    this.selectResidue(obj.atoms.chains[atomIndex], obj.atoms.resis[atomIndex], mods);
  }

  /** Select a residue, honoring modifier keys:
   *  plain → replace `sele`; Shift → range from the anchor; Cmd/Ctrl → add. */
  private selectResidue(chain: string, resi: number, mods: { range: boolean; add: boolean }): void {
    const hasSele = !!this.lastScene?.selections.includes("sele");
    if (mods.range && this.selAnchor && this.selAnchor.chain === chain) {
      const lo = Math.min(this.selAnchor.resi, resi);
      const hi = Math.max(this.selAnchor.resi, resi);
      this.handlers.onCommand(`select sele, chain ${chain} and resi ${lo}-${hi}`);
      return; // keep the anchor so the range can be re-dragged
    }
    if (mods.add && hasSele) {
      this.handlers.onCommand(`select sele, sele or (chain ${chain} and resi ${resi})`);
    } else {
      this.handlers.onCommand(`select sele, chain ${chain} and resi ${resi}`);
    }
    this.selAnchor = { chain, resi };
  }

  private cancelMeasure(): void {
    if (this.measureMode) {
      this.measureMode = null;
      this.measurePicks = [];
      this.hideToast();
    }
  }

  // ---- script editor (left dock, toggleable) ----

  private buildScriptEditor(): HTMLElement {
    this.scriptGutter = el("div", { className: "vm-gutter" });
    this.scriptArea = el("textarea", {
      className: "vm-code", spellcheck: false, value: STARTER_SCRIPT,
    }) as HTMLTextAreaElement;
    this.scriptArea.addEventListener("input", () => this.syncGutter());
    this.scriptArea.addEventListener("scroll", () => {
      this.scriptGutter.scrollTop = this.scriptArea.scrollTop;
    });
    this.scriptArea.addEventListener("keydown", (e) => this.onScriptKey(e));

    const runAll = el("button", { className: "vm-btn", textContent: "▶▶ Run All", title: "Shift+Cmd/Ctrl+Enter", onclick: () => this.runScriptAll() });
    const runSel = el("button", { className: "vm-btn", textContent: "▶ Run", title: "Cmd/Ctrl+Enter — selection or current line", onclick: () => this.runScriptSelection() });
    const close = el("button", { className: "vm-x", textContent: "✕", title: "hide", onclick: () => this.toggleScript() });

    this.scriptPanel = el("div", { className: "vm-editor vm-card" }, [
      el("div", { className: "vm-editor-head" }, [
        el("span", { className: "vm-title", textContent: "Script" }),
        el("span", { className: "vm-spacer" }), runSel, runAll, close,
      ]),
      el("div", { className: "vm-code-wrap" }, [this.scriptGutter, this.scriptArea]),
      el("div", { className: "vm-editor-hint", textContent: "⌘/Ctrl+Enter: run line/selection · ⇧: run all" }),
    ]);
    this.scriptPanel.style.display = "none";
    this.syncGutter();
    return this.scriptPanel;
  }

  private toggleScript(): void {
    this.scriptVisible = !this.scriptVisible;
    this.scriptPanel.style.display = this.scriptVisible ? "flex" : "none";
    if (this.scriptVisible) {
      this.syncGutter();
      this.scriptArea.focus();
    }
  }

  private syncGutter(): void {
    const n = this.scriptArea.value.split("\n").length;
    this.scriptGutter.textContent = Array.from({ length: n }, (_, i) => i + 1).join("\n");
    this.scriptGutter.scrollTop = this.scriptArea.scrollTop;
  }

  private onScriptKey(e: KeyboardEvent): void {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (e.shiftKey) this.runScriptAll();
      else this.runScriptSelection();
    } else if (e.key === "Tab") {
      e.preventDefault(); // keep focus; insert two spaces
      const ta = this.scriptArea;
      const s = ta.selectionStart;
      ta.value = ta.value.slice(0, s) + "  " + ta.value.slice(ta.selectionEnd);
      ta.selectionStart = ta.selectionEnd = s + 2;
      this.syncGutter();
    }
  }

  private runScriptAll(): void {
    this.handlers.onRunScript(this.scriptArea.value);
  }

  /** Run the selected lines, or the current line if there's no selection. */
  private runScriptSelection(): void {
    const ta = this.scriptArea;
    const v = ta.value;
    const lineStart = v.lastIndexOf("\n", ta.selectionStart - 1) + 1;
    let lineEnd = v.indexOf("\n", ta.selectionEnd);
    if (lineEnd === -1) lineEnd = v.length;
    this.handlers.onRunScript(v.slice(lineStart, lineEnd));
    // No selection? advance the caret to the next line for rapid stepping.
    if (ta.selectionStart === ta.selectionEnd) {
      const next = Math.min(lineEnd + 1, v.length);
      ta.selectionStart = ta.selectionEnd = next;
    }
  }

  // ---- right data panel ----

  private buildRightPanel(): HTMLElement {
    return el("div", { className: "vm-right vm-card vm-scroll" }, [
      this.section("Objects", this.objectsEl),
      this.section("Selections", this.selectionsEl),
      this.section("Sequence", this.sequenceEl),
    ]);
  }

  private section(title: string, body: Node): HTMLElement {
    return el("div", { className: "vm-section" }, [
      el("div", { className: "vm-title", textContent: title }), body,
    ]);
  }

  // ---- bottom dock ----

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
      el("span", { className: "vm-title", textContent: "State" }), playBtn, this.trajSlider, this.trajLabel,
    ]) as HTMLDivElement;

    const input = el("input", {
      className: "vm-console-input",
      placeholder: "command…  (e.g. show sticks, chain A · color spectrum · select site, resn HOH)",
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.cancelMeasure();
      else if (e.key === "Enter" && input.value.trim()) {
        const c = input.value.trim();
        this.handlers.onCommand(c);
        if (this.history[this.history.length - 1] !== c) this.history.push(c);
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
          input.value = this.history[++this.historyIdx];
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
        ? scene.objects.map((o) => this.objectRow(o))
        : [el("div", { className: "vm-empty", textContent: "Open a structure (File ▸ Demo / Fetch)" })]),
    );
    this.renderSelections(scene);
    this.renderSequence(scene);
  }

  private objectRow(o: DecodedScene["objects"][number]): HTMLElement {
    const eye = el("button", {
      className: "vm-x vm-eye",
      textContent: o.visible ? "◉" : "◯",
      title: o.visible ? "hide object" : "show object",
      onclick: () => this.handlers.onCommand(`${o.visible ? "disable" : "enable"} ${o.name}`),
    });
    const nameEl = el("span", {
      className: "name", title: "click to select the whole object",
      onclick: () => this.handlers.onCommand(`select sele, ${o.name}`),
    }, [o.name, el("span", { className: "meta", textContent: ` ${o.nAtoms} atoms` })]);
    const del = el("button", {
      className: "vm-x", textContent: "✕", title: `delete ${o.name}`,
      onclick: () => this.handlers.onCommand(`delete ${o.name}`),
    });
    return el("div", { className: "vm-row vm-obj" + (o.visible ? "" : " hidden") }, [eye, nameEl, del]);
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
    this.target = this.target === name ? null : name;
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
      className: "name", textContent: name, title: "click to target with Representation/Color",
      onclick: () => this.setTarget(name),
    });
    return el("div", { className: "vm-row vm-sel" + (active ? " active" : "") }, [
      nameEl,
      el("button", { className: "vm-x", textContent: "✎", title: "rename", onclick: () => this.beginRename(name, nameEl) }),
      el("button", { className: "vm-x", textContent: "✕", title: "delete", onclick: () => this.handlers.onCommand(`deselect ${name}`) }),
    ]);
  }

  private beginRename(oldName: string, nameEl: HTMLElement): void {
    const input = el("input", { className: "vm-rename", value: oldName });
    nameEl.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = (apply: boolean) => {
      if (done) return;
      done = true;
      const next = input.value.trim();
      if (apply && next && next !== oldName) {
        if (this.target === oldName) this.setTarget(next, false);
        this.handlers.onCommand(`set_name ${oldName}, ${next}`);
      } else if (this.lastScene) {
        this.renderSelections(this.lastScene);
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
            title: `${obj.name} ${r.resn}${r.resi} (chain ${chain})  ·  shift=range, ⌘=add`,
            onclick: (e: MouseEvent) =>
              this.selectResidue(chain, r.resi, { range: e.shiftKey, add: e.metaKey || e.ctrlKey }),
          }),
        );
        rows.push(el("div", { className: "vm-seq-row" }, [
          el("span", { className: "vm-seq-label", textContent: `${obj.name}/${chain}` }), ...letters,
        ]));
      }
    }
    this.sequenceEl.replaceChildren(...(rows.length ? rows : [el("div", { className: "vm-empty", textContent: "—" })]));
  }

  renderLog(log: LogLine[]): void {
    this.logEl.replaceChildren(
      ...log.map((line) =>
        el("div", {
          className: "vm-log-line" + (line.level === "error" ? " err" : line.message.startsWith(">") ? " cmd" : ""),
          textContent: line.message,
        }),
      ),
    );
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  private toast(message: string, sticky = false): void {
    this.hintEl.textContent = message;
    this.hintEl.style.display = "block";
    if (!sticky) window.setTimeout(() => this.hideToast(), 2500);
  }

  private hideToast(): void {
    this.hintEl.style.display = "none";
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
