import { Route, Routes, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import DataPage from './pages/DataPage'
import RoutePage from './pages/RoutePage'
import PacketPage from './pages/PacketPage'

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <div className="flex-1 p-4">
        <Routes>
          <Route path="/data" element={<DataPage />} />
          <Route path="/route" element={<RoutePage />} />
          <Route path="/packet" element={<PacketPage />} />
          <Route path="*" element={<Navigate to="/data" replace />} />
        </Routes>
      </div>
    </div>
  )
}
