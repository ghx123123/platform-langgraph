// Quiz/index.ts - 测验组件导出

export { QuizInterface } from './QuizInterface';
export { QuizResult } from './QuizResult';

export type {
  QuizWithQuestions,
  QuizResult as QuizResultType,
  QuizAnswer,
  QuizQuestion,
  QuestionType,
  QuizStatus,
  GenerateQuizOptions,
  QuizProgress,
} from '../../services/quizApi';

export {
  fetchQuiz,
  generateQuiz,
  submitQuiz,
  fetchQuizResults,
  startQuiz,
  saveQuizProgress,
  loadQuizProgress,
  clearQuizProgress,
  getQuestionTypeConfig,
  getDifficultyConfig,
  getScoreLevelConfig,
  formatTime,
} from '../../services/quizApi';
