import type { Order } from '../types';

interface OrderCardProps {
  order: Order;
}

function OrderCard({ order }: OrderCardProps) {
  return (
    <div className="order-card">
      <p>주문번호: {order.id}</p>
      <p>상태: {order.status}</p>
    </div>
  );
}

export default OrderCard;