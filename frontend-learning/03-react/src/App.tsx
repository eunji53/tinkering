import { useState } from 'react';
import { orders } from './types';
import type { OrderStatus } from './types';
import OrderList from './components/OrderList';
import './App.css';

type FilterStatus = OrderStatus | '전체';

function App() {
  const [filter, setFilter] = useState<FilterStatus>('전체');

  const filteredOrders =
    filter === '전체' ? orders : orders.filter((order) => order.status === filter);

  return (
    <div>
      <h1>주문 목록</h1>
      <div className="filters">
        <button onClick={() => setFilter('전체')}>전체</button>
        <button onClick={() => setFilter('주문접수')}>주문접수</button>
        <button onClick={() => setFilter('배송중')}>배송중</button>
        <button onClick={() => setFilter('배송완료')}>배송완료</button>
      </div>
      <OrderList orders={filteredOrders} />
    </div>
  );
}

export default App;