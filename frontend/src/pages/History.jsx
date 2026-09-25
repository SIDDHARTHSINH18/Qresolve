import Panel from '../components/ui/Panel.jsx'
import HistoryList from '../components/history/HistoryList.jsx'

export default function HistoryPage({ entries, onOpen, onRemove, onClear }) {
  return (
    <div className="page page-history">
      <Panel
        title="Debugging history"
        subtitle="Stored locally in this browser only · never contains credentials"
        actions={
          entries.length > 0 && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
              Clear History
            </button>
          )
        }
      >
        <HistoryList entries={entries} onOpen={onOpen} onRemove={onRemove} />
        <p className="help-text">
          Clicking a case reopens its code, error, diagnosis, fix and verification state from the
          stored backend response. Removing a case deletes it from local storage only.
        </p>
      </Panel>
    </div>
  )
}
