import type { NovaNewsFilter, NovaNewsStory } from '../types/novaNews';

export function storyMatchesFilter(story: NovaNewsStory, filter: NovaNewsFilter): boolean {
  if (filter === 'all') return true;
  return story.tags.includes(filter);
}

export function filterStories(
  stories: NovaNewsStory[],
  filter: NovaNewsFilter,
): NovaNewsStory[] {
  return stories.filter((story) => storyMatchesFilter(story, filter));
}
