import { useParams } from 'react-router-dom'

export default function AgentRunDetailPage() {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-brand-800">Agent Run: {id}</h1>
      <p className="mt-2 text-sm text-gray-600">
        Coming soon — see{' '}
        <a
          href="https://github.com/olafkfreund/github_discovery_repporting/issues/4"
          className="text-brand-700 underline"
        >
          epic #4
        </a>
        .
      </p>
    </div>
  )
}
