/**
 * Modules menu — show/hide registered modules; persistence via useModuleVisibility.
 */
import { listModules, type NovaModule } from '../workspace/registry';

interface Props {
  visibility: Record<string, boolean>;
  onToggle: (id: string, visible: boolean) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ModulesMenu({ visibility, onToggle, open, onOpenChange }: Props) {
  const modules = listModules();

  return (
    <div className="modules-menu" data-testid="modules-menu">
      <button
        type="button"
        className={`tab modules-menu__toggle${open ? ' active' : ''}`}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => onOpenChange(!open)}
      >
        Modules
      </button>
      {open && (
        <div className="modules-menu__panel" role="menu" data-testid="modules-menu-panel">
          {modules.map((m: NovaModule) => {
            const checked = visibility[m.id] !== false;
            return (
              <label key={m.id} className="modules-menu__item" role="menuitemcheckbox" aria-checked={checked}>
                <input
                  type="checkbox"
                  checked={checked}
                  data-module-toggle={m.id}
                  onChange={e => onToggle(m.id, e.target.checked)}
                />
                <span>{m.title}</span>
                <span className="modules-menu__placement">{m.defaultPlacement}</span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
