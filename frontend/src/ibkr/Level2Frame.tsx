/**
 * The Level 2 pane's root: it carries the operator's size (`data-l2-size`, which the stylesheet turns into
 * the pane's type and row scale) and opens the size menu on a right click. Both ladders -- the live book and
 * the Sim's recorded one -- render inside it, so one choice reaches every pane.
 */
import { useCallback, useState, type HTMLAttributes, type MouseEvent, type ReactNode } from 'react';
import { Level2SizeMenu } from './Level2SizeMenu';
import { setLevel2Size, useLevel2Size, type Level2Size } from './level2Size';

interface Props extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Level2Frame({ children, className, ...rest }: Props) {
  const size = useLevel2Size();
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);

  const onContextMenu = useCallback((event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    setMenu({ x: event.clientX, y: event.clientY });
  }, []);
  const closeMenu = useCallback(() => setMenu(null), []);
  const pick = useCallback((next: Level2Size) => {
    setLevel2Size(next);
    setMenu(null);
  }, []);

  return (
    <div
      {...rest}
      className={className ? `das-l2 ${className}` : 'das-l2'}
      data-l2-size={size}
      onContextMenu={onContextMenu}
    >
      {children}
      {menu && <Level2SizeMenu x={menu.x} y={menu.y} size={size} onPick={pick} onClose={closeMenu} />}
    </div>
  );
}
