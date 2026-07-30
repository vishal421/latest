import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { X } from "lucide-react";
import { NAV } from "../navConfig";

/**
 * Desktop: fixed, starts collapsed (68px, icons only). On mouseEnter
 * it expands to 272px as an overlay (position: fixed, higher z-index)
 * -- the main content's left padding never changes, so nothing shifts.
 * Collapses automatically on mouseLeave.
 *
 * Mobile (<768px): no hover. A hamburger in TopNav toggles this same
 * component into a slide-out drawer instead (see `mobileOpen` prop).
 */
export default function Sidebar({ mobileOpen, onCloseMobile }) {
  const [hovered, setHovered] = useState(false);
  const location = useLocation();
  const expanded = hovered || mobileOpen;

  const isActiveGroup = (item) => {
    if (item.path) return location.pathname === item.path;
    return item.children?.some((c) => location.pathname === c.path);
  };

  return (
    <>
      {mobileOpen && <div className="sidebar-scrim" onClick={onCloseMobile} />}
      <nav
        className={`sidebar ${expanded ? "sidebar-expanded" : ""} ${mobileOpen ? "sidebar-mobile-open" : ""}`}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <div className="sidebar-brand">
          <span className="sidebar-brand-mark" />
          {expanded && <span className="sidebar-brand-text">InfraOS</span>}
          {mobileOpen && (
            <button className="icon-btn sidebar-mobile-close" onClick={onCloseMobile} aria-label="Close menu">
              <X size={18} />
            </button>
          )}
        </div>

        <div className="sidebar-scroll">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = isActiveGroup(item);
            if (!item.children) {
              return (
                <NavLink
                  key={item.key}
                  to={item.path}
                  className={`sidebar-item ${active ? "sidebar-item-active" : ""}`}
                  title={!expanded ? item.label : undefined}
                  onClick={onCloseMobile}
                >
                  <Icon size={18} className="sidebar-icon" />
                  {expanded && <span className="sidebar-label">{item.label}</span>}
                </NavLink>
              );
            }
            return (
              <div key={item.key} className="sidebar-group">
                <div className={`sidebar-item sidebar-group-head ${active ? "sidebar-item-active" : ""}`}
                     title={!expanded ? item.label : undefined}>
                  <Icon size={18} className="sidebar-icon" />
                  {expanded && <span className="sidebar-label">{item.label}</span>}
                </div>
                {expanded && (
                  <div className="sidebar-submenu">
                    {item.children.map((child) => (
                      <NavLink
                        key={child.key}
                        to={child.path}
                        className={({ isActive }) => `sidebar-subitem ${isActive ? "sidebar-subitem-active" : ""}`}
                        onClick={onCloseMobile}
                      >
                        {child.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </nav>
    </>
  );
}
