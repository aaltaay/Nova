import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ReviewApp } from './ReviewApp';
import './review.css';

export function mountReview(): void {
  const root = document.getElementById('root');
  if (!root) {
    console.error('#root missing');
    return;
  }
  document.documentElement.classList.add('review-root');
  document.body.classList.add('review-root');
  createRoot(root).render(
    <StrictMode>
      <ReviewApp />
    </StrictMode>,
  );
}
