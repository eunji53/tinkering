type OrderStatus = '배송중' | '배송완료' | '주문접수';

interface Order {
  id: string;
  status: OrderStatus;
}

const orders: Order[] = [
  { id: 'A1001', status: '배송중' },
  { id: 'A1002', status: '배송완료' },
  { id: 'A1003', status: '주문접수' },
  // { id: 'A1004', status: '배송준비중' }, // 일부러 틀린 값 (Step 3 실습용)
];

const nextStatus: Record<OrderStatus, OrderStatus | null> = {
  '주문접수' : '배송중',
  '배송중' : '배송완료',
  '배송완료' : null,
}

function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  return nextStatus[from] === to;
}

console.log(canTransition('주문접수', '배송중'));
console.log(canTransition('배송중', '주문접수'));
console.log(canTransition('배송완료', '주문접수'));
