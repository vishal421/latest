export default function Card({ title, action, children, className = "", padding = true }) {
  return (
    <div className={`ui-card ${className}`}>
      {(title || action) && (
        <div className="ui-card-head">
          {title && <h3 className="ui-card-title">{title}</h3>}
          {action}
        </div>
      )}
      <div className={padding ? "ui-card-body" : ""}>{children}</div>
    </div>
  );
}
