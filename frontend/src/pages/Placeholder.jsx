import EmptyState from "../components/EmptyState";

export default function Placeholder({ icon, title, description }) {
  return (
    <div>
      <div className="page-head">
        <div><h1>{title}</h1></div>
      </div>
      <div className="ui-card">
        <EmptyState icon={icon} title={`${title} is coming soon`} description={description} />
      </div>
    </div>
  );
}
