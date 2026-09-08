import type { Order } from '../types';
import OrderCard from './OrderCard';

interface OrderListProps {
  orders: Order[];
}

function OrderList({ orders }: OrderListProps) {
  return (
    <div className="order-list">
      {orders.map((order) => (
        <OrderCard key={order.id} order={order} />
      ))}
    </div>
  );
}

export default OrderList;