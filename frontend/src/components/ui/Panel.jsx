export default function Panel({ title, subtitle, actions, children, className = '', step }) {
  return (
    <section className={`panel ${className}`} aria-label={typeof title === 'string' ? title : undefined}>
      {(title || actions) && (
        <header className="panel-header">
          <div className="panel-titles">
            {title && (
              <h2 className="panel-title">
                {step && <span className="panel-step" aria-hidden="true">{step}</span>}
                {title}
              </h2>
            )}
            {subtitle && <p className="panel-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      <div className="panel-body">{children}</div>
    </section>
  )
}
