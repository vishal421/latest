/**
 * fields: [{ key, label, type: 'text'|'select', options?, placeholder? }]
 * value: object keyed by field.key
 * onChange(key, value), onSubmit()
 */
export default function FilterBar({ fields, value, onChange, onSubmit, submitLabel = "Search", extra }) {
  return (
    <form className="filter-bar" onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
      <div className="filter-bar-fields">
        {fields.map((f) => (
          <div key={f.key} className="filter-field">
            <label>{f.label}</label>
            {f.type === "select" ? (
              <select value={value[f.key] ?? ""} onChange={(e) => onChange(f.key, e.target.value)}>
                <option value="">{f.placeholder || "Any"}</option>
                {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : (
              <input
                type={f.type || "text"}
                value={value[f.key] ?? ""}
                placeholder={f.placeholder}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>
      <div className="filter-bar-actions">
        {extra}
        <button type="submit" className="btn-primary">{submitLabel}</button>
      </div>
    </form>
  );
}
