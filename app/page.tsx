import { FarmerDashboard } from './components/FarmerDashboard';
import { NotificationBridge } from './features/notifications/presentation/NotificationBridge';

export default function Home() {
  return <>
    <FarmerDashboard />
    <NotificationBridge />
  </>;
}
