import { el } from "./dom";

// A dependency-free dropdown menu bar.
export type MenuItem =
  | { kind: "action"; label: string; run: () => void }
  | { kind: "submenu"; label: string; items: MenuItem[] }
  | { kind: "checkbox"; label: string; checked: () => boolean; toggle: () => void }
  | { kind: "separator" };

export interface MenuDef {
  label: string;
  items: MenuItem[];
}

export class Menubar {
  readonly element: HTMLElement;
  private openDropdown: HTMLElement | null = null;

  constructor(defs: MenuDef[]) {
    const menus = defs.map((def) => this.buildMenu(def));
    this.element = el("div", { className: "vm-menus" }, menus);
    // Click anywhere outside closes the open menu.
    document.addEventListener("click", (e) => {
      if (this.openDropdown && !this.element.contains(e.target as Node)) this.close();
    });
  }

  private buildMenu(def: MenuDef): HTMLElement {
    const dropdown = el("div", { className: "vm-dropdown" }, this.buildItems(def.items));
    const button = el("button", { className: "vm-menu-btn", textContent: def.label });
    const menu = el("div", { className: "vm-menu" }, [button, dropdown]);
    button.onclick = (e) => {
      e.stopPropagation();
      if (this.openDropdown === dropdown) {
        this.close();
      } else {
        this.open(menu, dropdown);
      }
    };
    // If a menu is already open, hovering another top-level switches to it.
    button.onmouseenter = () => {
      if (this.openDropdown && this.openDropdown !== dropdown) this.open(menu, dropdown);
    };
    return menu;
  }

  private buildItems(items: MenuItem[]): Node[] {
    return items.map((item) => {
      if (item.kind === "separator") return el("div", { className: "vm-menu-sep" });
      if (item.kind === "submenu") {
        const sub = el("div", { className: "vm-dropdown vm-submenu" }, this.buildItems(item.items));
        return el("div", { className: "vm-menu-item vm-has-sub" }, [
          el("span", { textContent: item.label }),
          el("span", { className: "vm-arrow", textContent: "▸" }),
          sub,
        ]);
      }
      if (item.kind === "checkbox") {
        const row = el("div", { className: "vm-menu-item" }, [
          el("span", { className: "vm-check", textContent: item.checked() ? "✓" : "" }),
          el("span", { textContent: item.label }),
        ]);
        row.onclick = (e) => {
          e.stopPropagation();
          item.toggle();
          (row.firstChild as HTMLElement).textContent = item.checked() ? "✓" : "";
        };
        return row;
      }
      const row = el("div", { className: "vm-menu-item" }, [el("span", { textContent: item.label })]);
      row.onclick = (e) => {
        e.stopPropagation();
        item.run();
        this.close();
      };
      return row;
    });
  }

  private open(menu: HTMLElement, dropdown: HTMLElement): void {
    this.close();
    menu.classList.add("open");
    dropdown.classList.add("open");
    this.openDropdown = dropdown;
  }

  private close(): void {
    if (!this.openDropdown) return;
    this.openDropdown.classList.remove("open");
    this.openDropdown.closest(".vm-menu")?.classList.remove("open");
    this.openDropdown = null;
  }
}
