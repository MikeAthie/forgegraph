import Header from "../components/Header";
import ProtectedRoute from "../components/ProtectedRoute";

export default function RunsPage() {
  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg border border-gray-200 p-10 text-center">
            <h1 className="text-2xl font-bold text-gray-900">Runs</h1>
            <p className="mt-2 text-gray-600">Run history and logs will appear here.</p>
            <p className="mt-1 text-sm text-gray-400">Coming in Phase 2</p>
          </div>
        </main>
      </div>
    </ProtectedRoute>
  );
}

