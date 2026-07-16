/**
 * Modules menu — show/hide + panel order (↑↓); persistence via visibility + layout store.
 */
import { getModule, listModules, type NovaModule } from '../workspace/registry';
import type { LayoutSlotId } from '../workspace/layoutStore';

interface Props {
  visibility: Record<string, boolean>;
  onToggle: (id: string, visible: boolean) => void;
  /** Ordered module ids for the active reorder slot. */
  panelOrder: string[];
  reorderSlot: LayoutSlotId;
  onReorderSlotChange: (slot: LayoutSlotId) => void;
  onMove: (moduleId: string, direction: 'up' | 'down') => void;
  onResetLayout: () => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ModulesMenu({
  visibility,
  onToggle,
  panelOrder,
  reorderSlot,
  onReorderSlotChange,
  onMove,
  onResetLayout,
  open,
  onOpenChange,
}: Props) {
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
              <label
                key={m.id}
                className="modules-menu__item"
                role="menuitemcheckbox"
                aria-checked={checked}
              >
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

          <div className="modules-menu__section" data-testid="layout-order-section">
            <div className="modules-menu__section-title">Panel order</div>
            <div className="modules-menu__slot-tabs" role="tablist" aria-label="Layout slot">
              <button
                type="button"
                role="tab"
                className={reorderSlot === 'side_panel' ? 'active' : ''}
                aria-selected={reorderSlot === 'side_panel'}
                data-layout-slot="side_panel"
                onClick={() => onReorderSlotChange('side_panel')}
              >
                Side panel
              </button>
              <button
                type="button"
                role="tab"
                className={reorderSlot === 'stock_view' ? 'active' : ''}
                aria-selected={reorderSlot === 'stock_view'}
                data-layout-slot="stock_view"
                onClick={() => onReorderSlotChange('stock_view')}
              >
                Stock view
              </button>
            </div>
            <ul className="modules-menu__order-list" data-testid="layout-order-list">
              {panelOrder.map((id, index) => {
                const title = getModule(id)?.title ?? id;
                return (
                  <li key={id} className="modules-menu__order-item" data-layout-order-id={id}>
                    <span className="modules-menu__order-label">{title}</span>
                    <span className="modules-menu__order-actions">
                      <button
                        type="button"
                        aria-label={`Move ${title} up`}
                        data-layout-move="up"
                        data-layout-move-id={id}
                        disabled={index === 0}
                        onClick={() => onMove(id, 'up')}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        aria-label={`Move ${title} down`}
                        data-layout-move="down"
                        data-layout-move-id={id}
                        disabled={index === panelOrder.length - 1}
                        onClick={() => onMove(id, 'down')}
                      >
                        ↓
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
            <button
              type="button"
              className="modules-menu__reset"
              data-testid="layout-reset"
              onClick={onResetLayout}
            >
              Reset layout
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
