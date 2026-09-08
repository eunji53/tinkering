# 2단계 — TypeScript 기초

커리큘럼: [../docs/curriculum.md](../docs/curriculum.md#2단계--typescript-기초)

목표: 1단계 주문 데이터를 TS로 옮기고 상태값을 union 타입으로 정의, 상태 전이가 가능한 조합만 허용하는 타입/함수 작성하기.

실습 파일: 이 폴더의 `orders.ts`

### 파일 내 코드 작성 순서 (일반적인 관례)

`function`은 호이스팅되고 `const`도 "호출/참조되는 시점"에만 선언돼 있으면 되기 때문에, 대부분의 경우 파일 안에서 타입/데이터/함수의 작성 순서는 실행 결과에 영향을 주지 않음. 그래도 사람이 위에서 아래로 읽을 때 자연스럽도록 아래 순서가 관례:

1. **타입/인터페이스 정의** (`type OrderStatus`, `interface Order`) — 이 파일에서 다루는 데이터 모양을 먼저 보여줌
2. **데이터/상수** (`orders`, `nextStatus`) — 실제 값
3. **함수(로직)** (`canTransition`) — 데이터를 가지고 하는 동작
4. **실행/테스트 코드** (`console.log(...)`) — 보통 맨 아래. 실무에서는 이런 실행 코드를 파일에 남기지 않고 별도 테스트 파일로 분리하는 경우가 많음
5. **`export`** — 관례상 파일 맨 위 또는 맨 아래 중 하나로 통일

`orders.ts`는 이미 이 순서(타입 → 데이터 → 함수 → 실행 → export)를 따르고 있음.

---

## Step 1 — 환경 준비

```bash
cd 02-typescript
npm init -y
npm install -D typescript
```

**개념 포인트**
- `npm init -y`: 이 폴더를 npm 프로젝트로 만듦 (`package.json` 생성)
- `npm install -D typescript`: TypeScript 컴파일러를 이 폴더 안에 설치 (devDependency) — 이걸로 타입 에러를 실행 없이 미리 잡아낼 수 있음
- `node_modules/`는 프로젝트 `.gitignore`에 이미 등록돼 있어서 git에는 안 올라감

## Step 2 — 주문 데이터를 타입으로 표현하기

```ts
type OrderStatus = '배송중' | '배송완료' | '주문접수';

interface Order {
  id: string;
  status: OrderStatus;
}

const orders: Order[] = [
  { id: 'A1001', status: '배송중' },
  { id: 'A1002', status: '배송완료' },
  { id: 'A1003', status: '주문접수' },
];
```

**개념 포인트**
- `type OrderStatus = 'A' | 'B' | 'C'`: **union 타입** — 이 변수는 저 셋 중 하나의 값만 가질 수 있음. JS에서는 그냥 문자열이라 아무 값이나 넣을 수 있었지만, 이제는 오타나 잘못된 상태값을 코드 작성 중에 바로 잡아줌
- `interface Order { id: string; status: OrderStatus; }`: **객체의 모양(shape)**을 정의. "Order 타입은 반드시 id(문자열)와 status(OrderStatus) 필드를 가져야 한다"는 규칙
- `const orders: Order[]`: `orders`는 "Order 타입 객체들의 배열"이라고 타입을 명시

**타입 체크 방법**: `02-typescript` 폴더 안에서

```bash
npx tsc --noEmit orders.ts
```

에러 없이 조용히 끝나면 정상.

## Step 3 — 타입 에러 직접 확인해보기

`orders.ts`의 `orders` 배열에 union 타입(`OrderStatus`)에 없는 값을 일부러 넣어봄:

```ts
{ id: 'A1004', status: '배송준비중' }, // '배송중' | '배송완료' | '주문접수'에 없는 값
```

`npx tsc --noEmit orders.ts` 실행 결과:

```
orders.ts:12:18 - error TS2322: Type '"배송준비중"' is not assignable to type 'OrderStatus'.
  orders.ts:5:3 - The expected type comes from property 'status' which is declared here on type 'Order'
```

**에러 해석**
- `TS2322`: `"배송준비중"`이 `OrderStatus` 타입(세 값 중 하나)에 속하지 않아서 대입할 수 없다는 뜻
- 두 번째 줄은 근거: `Order` interface에서 `status: OrderStatus`로 선언했기 때문에 저 자리엔 세 값 외엔 못 들어감
- 줄/열 번호까지 정확히 짚어줘서, **실행하지 않고도(컴파일 시점에)** 잘못된 값을 코드 작성 중에 바로 잡아낼 수 있음 — JS였으면 이 코드는 그냥 실행됐다가 나중에 화면에 이상한 상태값이 찍히는 식으로 런타임에서야 문제가 드러났을 것

### 트러블슈팅 — "cannot redeclare block-scoped variable 'orders'" (ts(2451))

위 실습 중 VS Code 에디터에서 `orders` 밑에 빨간 밑줄이 뜨는 문제 발생. 툴팁 메시지:

```
cannot redeclare block-scoped variable 'orders'. ts(2451)
script.js(1,7): 'orders' was also declared here
```

**원인**: `orders.ts`와 `01-html-css-js/script.js` 둘 다 `import`/`export` 문이 없는 "스크립트" 파일이었음. TS/JS에서는 이런 파일의 최상위 선언이 파일별로 독립되지 않고 **전역 스코프(global scope)**를 공유함. 그래서 두 파일에 같은 이름(`orders`)이 있으니 "전역 변수를 두 번 선언했다"는 충돌 에러가 남 — `orders.ts` 코드 자체가 틀려서 나는 에러가 아니라, 두 파일이 스코프를 공유해버린 환경 문제였음.

**임시 해결**: `orders.ts` 맨 아래에 `export {};` 한 줄 추가 → 파일을 **모듈(module)**로 전환해 독립된 스코프를 갖게 함. 이후 빨간 밑줄 사라짐. (근본 해결은 아래 Step 4의 `tsconfig.json` 참고)

---

## Step 4 — 상태 전이 제한 함수

상태값이 `OrderStatus` 타입이기만 하면 되는 게 아니라, **순서**도 있어야 함 (주문접수 → 배송중 → 배송완료 순으로만, 역행 불가). TS 타입만으로는 이런 "값들 간의 순서 규칙"을 강제할 수 없어서, 함수(로직)로 직접 검사.

```ts
const nextStatus: Record<OrderStatus, OrderStatus | null> = {
  '주문접수': '배송중',
  '배송중': '배송완료',
  '배송완료': null,
};

function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  return nextStatus[from] === to;
}

console.log(canTransition('주문접수', '배송중'));   // true
console.log(canTransition('배송중', '주문접수'));   // false
console.log(canTransition('배송완료', '주문접수')); // false
```

**개념 포인트**
- `Record<OrderStatus, OrderStatus | null>`: TS 기본 제공 유틸리티 타입. "키는 `OrderStatus`, 값은 `OrderStatus` 또는 `null`인 객체"라는 뜻. `'배송완료': null`은 더 갈 다음 상태가 없다는 의미
- `function 함수이름(매개변수: 타입): 반환타입 { }`: TS 함수 선언 문법 — JS 함수 선언에 타입만 추가된 형태
- `function`으로 선언한 함수는 호이스팅되어 파일 어디에 적어도 동작하지만, `const nextStatus`는 호이스팅이 안 되므로 **호출 시점 기준으로** 먼저 선언돼 있어야 함 (지금처럼 맨 아래에서 호출하면 안전)

**실행 결과**: `true`, `false`, `false` — 정상 전이는 통과, 역행은 차단됨을 확인.

### 실행 방법 트러블슈팅

- `npx ts-node orders.ts`: 최신 TypeScript와 `ts-node`(v10.9.2) 간 호환성 버그로 `Cannot read properties of undefined (reading 'fileExists')` 에러 발생 → `ts-node` 대신 컴파일 후 실행하는 방식으로 우회
- `npx tsc orders.ts` 후 `node orders.js`: 컴파일러 기본 설정(옵션 없을 때)이 **ES 모듈 문법**으로 출력해서 `export {};`가 그대로 남는데, Node는 `package.json`에 `"type": "module"`이 없으면 `.js`를 CommonJS로 해석하려다 `export` 문법 자체를 못 읽고 `SyntaxError: Unexpected token 'export'` 발생 → `tsconfig.json`으로 근본 해결 (아래 참고)

### `tsconfig.json` — 이 폴더를 독립 TS 프로젝트로 만들기

```json
{
  "compilerOptions": {
    "module": "commonjs",
    "target": "ES2020",
    "strict": true
  },
  "include": ["*.ts"]
}
```

`tsconfig.json`은 "이 폴더가 하나의 TypeScript 프로젝트다"라고 선언하고, 그 프로젝트의 범위(어떤 파일이 포함되는지)와 컴파일 옵션을 지정하는 설정 파일.

- **`include: ["*.ts"]`**: 이 파일이 있으면 VS Code의 TS 언어 서버가 "이 폴더가 프로젝트 루트"라고 인식해서, 여기서 지정한 파일들만 하나의 프로그램으로 묶음. 형제 폴더(`../01-html-css-js/script.js`)는 이 프로젝트에 포함되지 않으므로 이름이 같아도(`orders`) 더 이상 충돌하지 않음 — Step 3에서 `export {};`로 임시 해결했던 문제의 **근본 원인**(전역 스코프 공유)을 아예 프로젝트 범위 분리로 없앤 것
- **`module: "commonjs"`**: 컴파일된 JS가 Node가 기본으로 이해하는 CommonJS 형식(`require`/`module.exports`)으로 나오게 지정 → `npx tsc orders.ts`만 해도 `node orders.js`로 바로 실행 가능
- **`target: "ES2020"`**: 컴파일된 JS가 어떤 JS 버전 문법을 쓸지 지정
- **`strict: true`**: 타입 체크를 엄격하게 (모범 사례로 켜둠)

---

## 다음에 이어서 할 것

- 3단계(React)로 이동
- (선택) `orders.ts`의 실습용 주석 처리된 값(A1004)과 `export {};`는 이제 `tsconfig.json`이 스코프를 분리해주므로 그대로 둬도, 지워도 무방

## 진행 체크리스트

- [x] Step 1 — 환경 준비 (npm init, typescript 설치)
- [x] Step 2 — union 타입 + interface로 주문 데이터 타이핑
- [x] Step 3 — 타입 에러 직접 확인해보기 (+ 모듈/스크립트 스코프 충돌 트러블슈팅)
- [x] Step 4 — 상태 전이 제한 함수 (+ ts-node 호환성, tsconfig.json 트러블슈팅)
