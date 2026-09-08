# 3단계 — React (컴포넌트, props, state, 훅)

커리큘럼: [../docs/curriculum.md](../docs/curriculum.md#3단계--react-컴포넌트-props-state-훅)

목표: 1~2단계 데이터를 `OrderCard`, `OrderList` 컴포넌트로 분리하고, 상태 필터 버튼에 `useState` 적용하기.

실습 파일: 이 폴더의 `src/types.ts`, `src/components/OrderCard.tsx`, `src/components/OrderList.tsx`, `src/App.tsx`

---

## Step 1 — Vite + React 프로젝트 생성

```bash
cd 03-react
npm create vite@latest . -- --template react-ts
npm install
npm run dev
```

**진행 중 선택한 옵션**
- `Current directory is not empty` → **"Ignore files and continue"** 선택 (기존 `README.md`는 유지하고 Vite가 필요한 파일만 추가하려던 의도였으나, Vite 템플릿에 포함된 `README.md`는 결국 자체 내용으로 덮어써짐 — 지금 이 문서가 그걸 다시 학습용으로 정리한 것)
- `Which linter to use?` → **ESLint** 선택 (Oxlint보다 생태계/문서가 훨씬 많아 막혔을 때 검색하기 유리해서)

`npm run dev` 실행 후 `http://localhost:5173`에서 Vite + React 기본 화면(카운터 버튼) 뜨는 것 확인.

## Step 2 — 타입과 데이터 파일 (`src/types.ts`)

```ts
export type OrderStatus = '배송중' | '배송완료' | '주문접수';

export interface Order {
  id: string;
  status: OrderStatus;
}

export const orders: Order[] = [
  { id: 'A1001', status: '배송중' },
  { id: 'A1002', status: '배송완료' },
  { id: 'A1003', status: '주문접수' },
];
```

**개념 포인트**
- 2단계(`02-typescript`) 내용을 그대로 재사용하지 않은 이유: (1) `02-typescript`는 독립된 npm 프로젝트라 `03-react`에서 직접 `import` 불가, (2) 이번 단계 목표는 "렌더링"이라 상태 전이 로직(`nextStatus`, `canTransition`)은 필요 없어서 타입/데이터만 옮김
- `export`가 실제로 값을 내보내는 데 쓰임 — 2단계의 `export {};`(아무것도 안 내보내고 스코프만 분리)와 다른 용법

## Step 3 — `OrderCard` 컴포넌트 (`src/components/OrderCard.tsx`)

```tsx
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
```

**개념 포인트**
- `import type { Order }`: `Order`는 타입이라 실행 시점엔 존재하지 않음 → 타입 전용 import임을 명시
- `interface OrderCardProps`: 이 컴포넌트가 받을 props의 모양 정의
- `function OrderCard({ order }: OrderCardProps)`: 구조분해 할당으로 `props.order`를 바로 `order`로 꺼내 씀
- `{order.id}`: JSX 안 중괄호는 "여기 JS 표현식 값을 그대로 넣어라"라는 뜻
- `export default`: 컴포넌트 파일은 보통 기본 내보내기 하나만 사용

## Step 4 — `OrderList` 컴포넌트 (`src/components/OrderList.tsx`)

```tsx
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
```

**개념 포인트**
- `orders.map(...)`: 1단계에서 쓴 `map`과 동일 — 배열 원소마다 `<OrderCard />`를 하나씩 만들어 컴포넌트 배열 반환
- `key={order.id}`: 리스트 렌더링 시 필수 prop. React가 각 항목을 데이터와 대응시켜 추적하는 용도 (고유값 사용, 배열 index는 비추천). `OrderCard` 내부에서 `props.key`로 접근은 불가 — React 내부 전용

## Step 5 — `App.tsx`에서 렌더링

```tsx
import { orders } from './types';
import OrderList from './components/OrderList';
import './App.css';

function App() {
  return (
    <div>
      <h1>주문 목록</h1>
      <OrderList orders={orders} />
    </div>
  );
}

export default App;
```

기존 Vite 기본 화면 코드(`useState` 카운터, 로고 이미지 등) 전체 삭제하고 교체. 브라우저에서 주문 3건이 리스트로 뜨는 것 확인.

## Step 6 — `useState`로 상태 필터 버튼

```tsx
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
```

**개념 포인트**
- `useState`: React 훅(Hook). 컴포넌트가 다시 렌더링돼도 값을 유지해야 하는 "상태"를 관리. `const [값, 값을바꾸는함수] = useState(초기값)` 형태
- `useState<FilterStatus>('전체')`: 제네릭(`<FilterStatus>`)으로 상태 타입을 명시, 초기값은 `'전체'`
- `type FilterStatus = OrderStatus | '전체'`: 실제 주문 상태 셋 + "전체 보기"용 값 하나를 합친 union 타입
- `filter === '전체' ? orders : orders.filter(...)`: 삼항 연산자(`조건 ? A : B`). "전체"면 다 보여주고 아니면 1단계에서 쓴 `filter`로 걸러냄
- `onClick={() => setFilter('전체')}`: 화살표 함수로 감싸는 이유 — 그냥 `onClick={setFilter('전체')}`라고 쓰면 렌더링되는 즉시 실행돼버림. 클릭했을 때만 실행되게 하려면 함수로 한 번 감싸야 함 (자주 하는 실수)

---

## 진행 체크리스트

- [x] Step 1 — Vite + React 프로젝트 생성 (ESLint 선택)
- [x] Step 2 — 타입/데이터 파일 (`src/types.ts`)
- [x] Step 3 — `OrderCard` 컴포넌트
- [x] Step 4 — `OrderList` 컴포넌트
- [x] Step 5 — `App.tsx` 연결, 브라우저 렌더링 확인
- [x] Step 6 — `useState` 필터 버튼 (버튼 4개 클릭 시 리스트 정상 필터링 확인 완료)

## 다음에 이어서 할 것

- 4단계(Tailwind CSS)로 이동
