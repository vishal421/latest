import { useState } from "react";
import { Settings2 } from "lucide-react";

/**
 * columns: [{ key, label, render? }]
 * rows: array of plain objects
 * Column customization: a lightweight toggle list, per the Logs spec
 * ("Column Customization"). State is local to the table instance.
 */
export default function DataTable({ columns, rows, emptyLabel = "No data.", enableColumnPicker = false, onRowClick }) {
  const [visible, setVisible] = useState(() => new Set(columns.map((c) => c.key)));
  const [pickerOpen, setPickerOpen] = useState(false);
  const activeColumns = columns.filter((c) => visible.has(c.key));

  const toggle = (key) => {
    setVisible((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <div className="datatable-wrap">
      {enableColumnPicker && (
        <div className="datatable-toolbar">
          <button className="btn-ghost" onClick={() => setPickerOpen((v) => !v)}>
            <Settings2 size={14} /> Columns
          </button>
          {pickerOpen && (
            <div className="column-picker">
              {columns.map((c) => (
                <label key={c.key}>
                  <input type="checkbox" checked={visible.has(c.key)} onChange={() => toggle(c.key)} />
                  {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="datatable-scroll">
        <table className="datatable">
          <thead>
            <tr>{activeColumns.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={activeColumns.length} className="datatable-empty">{emptyLabel}</td></tr>
            ) : rows.map((row, i) => (
              <tr key={row.id ?? i} onClick={onRowClick ? () => onRowClick(row) : undefined}
                  style={onRowClick ? { cursor: "pointer" } : undefined}>
                {activeColumns.map((c) => (
                  <td key={c.key}>{c.render ? c.render(row) : row[c.key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
