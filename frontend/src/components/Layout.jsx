import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import TopNav from "./TopNav";

export default function Layout() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar mobileOpen={mobileMenuOpen} onCloseMobile={() => setMobileMenuOpen(false)} />
      <div className="app-main">
        <TopNav onOpenMobileMenu={() => setMobileMenuOpen(true)} />
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
