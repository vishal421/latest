import { useEffect, useState } from "react";
import Card from "../components/Card";
import { api } from "../api";

export default function Settings() {
  const [profile, setProfile] = useState({ admin_name: "", admin_email: "", organization_name: "" });
  const [licenseSummary, setLicenseSummary] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getProfile().then(setProfile).catch((e) => setError(e.message));
    api.getLicenseSummary().then(setLicenseSummary).catch(() => {});
  }, []);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true); setError(null); setSaved(false);
    try {
      const updated = await api.updateProfile(profile);
      setProfile(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  };

  return (
    <div>
      <div className="page-head">
        <div><h1>Settings</h1><p>Admin and organization profile, and a consolidated view of license posture.</p></div>
      </div>

      <Card title="Admin Profile">
        <form onSubmit={save}>
          <div className="grid-2col">
            <div><label>Name</label><input value={profile.admin_name} onChange={(e) => setProfile({ ...profile, admin_name: e.target.value })} placeholder="Vish" /></div>
            <div><label>Email</label><input type="email" value={profile.admin_email} onChange={(e) => setProfile({ ...profile, admin_email: e.target.value })} placeholder="you@company.com" /></div>
          </div>
          <div style={{ maxWidth: 340 }}>
            <label>Organization</label>
            <input value={profile.organization_name} onChange={(e) => setProfile({ ...profile, organization_name: e.target.value })} placeholder="Your Company" />
          </div>
          <button className="btn-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save changes"}</button>
          {saved && <span style={{ marginLeft: 10, fontSize: 12.5, color: "var(--good)" }}>Saved.</span>}
          {error && <div style={{ color: "var(--bad)", fontSize: 12.5, marginTop: 8 }}>{error}</div>}
          {profile.updated_at && <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 10 }}>Last updated {new Date(profile.updated_at).toLocaleString()}</div>}
        </form>
      </Card>

      <div style={{ height: 20 }} />
      <Card title="License Posture">
        {licenseSummary ? (
          <div className="grid-3col">
            <div className="stat-card ui-card">
              <div className="stat-label">Total Tracked</div>
              <div className="stat-value">{licenseSummary.total}</div>
            </div>
            <div className={`stat-card ui-card ${licenseSummary.expiring_within_30_days > 0 ? "stat-warn" : ""}`}>
              <div className="stat-label">Expiring within 30d</div>
              <div className="stat-value">{licenseSummary.expiring_within_30_days}</div>
            </div>
            <div className={`stat-card ui-card ${licenseSummary.expired > 0 ? "stat-bad" : ""}`}>
              <div className="stat-label">Expired</div>
              <div className="stat-value">{licenseSummary.expired}</div>
            </div>
          </div>
        ) : (
          <div className="empty" style={{ color: "var(--text-faint)", fontSize: 13 }}>No license data yet.</div>
        )}
      </Card>
    </div>
  );
}
