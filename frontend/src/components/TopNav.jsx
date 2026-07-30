import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Menu, Search, Bell, Settings, ChevronDown } from "lucide-react";

export default function TopNav({ onOpenMobileMenu }) {
  const [query, setQuery] = useState("");
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const navigate = useNavigate();

  const notifications = [
    { id: 1, text: "edge-fw-01 HA peer unreachable", time: "4m ago" },
    { id: 2, text: "License expiring in 9 days — dc-fw-02", time: "1h ago" },
    { id: 3, text: "Configuration committed by config_admin", time: "3h ago" },
  ];

  return (
    <header className="topnav">
      <button className="icon-btn topnav-hamburger" onClick={onOpenMobileMenu} aria-label="Open menu">
        <Menu size={20} />
      </button>

      <div className="topnav-search">
        <Search size={15} />
        <input
          placeholder="Search devices, logs, policies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="topnav-actions">
        <div className="topnav-dropdown-wrap">
          <button className="icon-btn" onClick={() => { setNotifOpen((v) => !v); setProfileOpen(false); }} aria-label="Notifications">
            <Bell size={18} />
            <span className="topnav-badge-dot" />
          </button>
          {notifOpen && (
            <div className="topnav-dropdown">
              <div className="topnav-dropdown-title">Notifications</div>
              {notifications.map((n) => (
                <div key={n.id} className="topnav-dropdown-row">
                  <div>{n.text}</div>
                  <div className="topnav-dropdown-time">{n.time}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <button className="icon-btn" onClick={() => navigate("/settings")} aria-label="Settings">
          <Settings size={18} />
        </button>

        <div className="topnav-dropdown-wrap">
          <button className="topnav-profile" onClick={() => { setProfileOpen((v) => !v); setNotifOpen(false); }}>
            <span className="topnav-avatar">VS</span>
            <span className="topnav-profile-name">Vish</span>
            <ChevronDown size={14} />
          </button>
          {profileOpen && (
            <div className="topnav-dropdown">
              <div className="topnav-dropdown-row">Profile</div>
              <div className="topnav-dropdown-row">Preferences</div>
              <div className="topnav-dropdown-row">Sign out</div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
