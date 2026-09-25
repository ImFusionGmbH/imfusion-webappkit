import { useEffect, useState } from 'react';
import type { Menu, MenuItem } from '@imfusion/sdk';
import { useContextMenu } from '@imfusion/sdk-react';

function ContextMenuItemView({ item, close }: { item: MenuItem; close(): void }) {
  if (item.isSeparator()) return <div className="context-menu-separator" />;
  if (item.isSubmenu()) {
    const submenu = item.getSubmenu();
    return (
      <div className="context-menu-item context-menu-submenu">
        <span>{submenu.title()}</span><span className="context-menu-submenu-indicator">▶</span>
        <div className="context-submenu">
          {Array.from(submenu.items()).map((child, index) => <ContextMenuItemView key={index} item={child} close={close} />)}
        </div>
      </div>
    );
  }
  const action = item.getAction();
  return (
    <button
      className="context-menu-item"
      title={action.description()}
      onClick={() => { action.activationCallback(); close(); }}
    >
      {(action.type() === 'checkable' || action.type() === 'radio') && (
        <span className="context-menu-check">{action.isChecked() ? '●' : '○'}</span>
      )}
      {action.title()}
    </button>
  );
}

export function ContextMenuOverlay() {
  const [menu, setMenu] = useState<{ value: Menu; x: number; y: number } | null>(null);
  useContextMenu((value, event) => {
    const pointer = event as MouseEvent;
    setMenu({ value, x: pointer.clientX, y: pointer.clientY });
  });
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [menu]);
  if (!menu) return null;
  return (
    <div className="context-menu" style={{ left: menu.x, top: menu.y }} onMouseDown={(event) => event.stopPropagation()}>
      {Array.from(menu.value.items()).map((item, index) => <ContextMenuItemView key={index} item={item} close={() => setMenu(null)} />)}
    </div>
  );
}
