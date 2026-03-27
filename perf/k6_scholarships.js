import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: __ENV.VUS ? Number(__ENV.VUS) : 10,
  iterations: __ENV.ITERATIONS ? Number(__ENV.ITERATIONS) : 100,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
  },
};

const baseUrl = __ENV.BASE_URL || 'http://127.0.0.1:18080';
const scenario = __ENV.SCENARIO || 'eligibility';

function runSearch() {
  return http.get(
    `${baseUrl}/api/v1/scholarships/search?query=%EC%9E%A5%ED%95%99%EA%B8%88&limit=10`
  );
}

function runOpenList() {
  return http.get(`${baseUrl}/api/v1/scholarships/open?limit=10`);
}

function runEligibility() {
  return http.post(
    `${baseUrl}/api/v1/scholarships/eligibility`,
    JSON.stringify({
      profile: {
        gpa: 3.5,
        income_bracket: 6,
        enrollment_status: '재학생',
        grade_level: 3,
      },
      limit: 10,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );
}

export default function () {
  let response;
  if (scenario === 'search') {
    response = runSearch();
  } else if (scenario === 'open') {
    response = runOpenList();
  } else {
    response = runEligibility();
  }

  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
