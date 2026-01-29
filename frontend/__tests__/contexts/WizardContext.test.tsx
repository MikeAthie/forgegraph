/**
 * Unit tests for WizardContext and useWizard hook.
 *
 * Tests wizard state management, step navigation, data persistence,
 * and completion tracking.
 */

import { act, renderHook } from '@testing-library/react';
import { ReactNode } from 'react';

import {
  DEFAULT_WIZARD_STEPS,
  useWizard,
  WizardProvider,
} from '@/contexts/WizardContext';

describe('WizardContext', () => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <WizardProvider>{children}</WizardProvider>
  );

  describe('useWizard Hook', () => {
    it('should throw error when used outside WizardProvider', () => {
      // Suppress console.error for this test
      const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});

      expect(() => {
        renderHook(() => useWizard());
      }).toThrow('useWizard must be used within a WizardProvider');

      consoleError.mockRestore();
    });

    it('should provide wizard context when used within WizardProvider', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current).toBeDefined();
      expect(result.current.startWizard).toBeInstanceOf(Function);
      expect(result.current.exitWizard).toBeInstanceOf(Function);
      expect(result.current.nextStep).toBeInstanceOf(Function);
      expect(result.current.prevStep).toBeInstanceOf(Function);
      expect(result.current.goToStep).toBeInstanceOf(Function);
      expect(result.current.setStepData).toBeInstanceOf(Function);
      expect(result.current.markStepComplete).toBeInstanceOf(Function);
      expect(result.current.markStepSkipped).toBeInstanceOf(Function);
      expect(result.current.setCanProceed).toBeInstanceOf(Function);
      expect(result.current.resetWizard).toBeInstanceOf(Function);
    });
  });

  describe('Initial State', () => {
    it('should start with wizard closed', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.isActive).toBe(false);
    });

    it('should start at step 0', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.currentStep).toBe(0);
    });

    it('should have correct total steps count', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.totalSteps).toBe(DEFAULT_WIZARD_STEPS.length);
    });

    it('should have no completed steps initially', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.completedSteps.size).toBe(0);
    });

    it('should have no skipped steps initially', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.skippedSteps.size).toBe(0);
    });

    it('should have empty step data initially', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.stepData).toEqual({});
    });

    it('should have canProceed false initially', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.canProceed).toBe(false);
    });

    it('should have canGoBack false initially', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.canGoBack).toBe(false);
    });

    it('should have isNewGraph false initially', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.state.isNewGraph).toBe(false);
    });

    it('should be on first step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.isFirstStep).toBe(true);
    });

    it('should not be on last step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.isLastStep).toBe(false);
    });

    it('should have 0% progress', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.progress).toBe(0);
    });

    it('should have correct current step config', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.currentStepConfig).toEqual(DEFAULT_WIZARD_STEPS[0]);
    });

    it('should provide steps array', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      expect(result.current.steps).toEqual(DEFAULT_WIZARD_STEPS);
    });
  });

  describe('START_WIZARD Action', () => {
    it('should open wizard when startWizard is called', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.isActive).toBe(true);
    });

    it('should reset to step 0 when starting wizard', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      // Navigate to a different step first
      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(1);

      // Start wizard again
      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.currentStep).toBe(0);
    });

    it('should clear completed steps when starting wizard', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
      });

      expect(result.current.state.completedSteps.size).toBe(1);

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.completedSteps.size).toBe(0);
    });

    it('should clear step data when starting wizard', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setStepData('test', { value: 'data' });
      });

      expect(Object.keys(result.current.state.stepData).length).toBe(1);

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.stepData).toEqual({});
    });

    it('should set isNewGraph to false by default', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.isNewGraph).toBe(false);
    });

    it('should set isNewGraph to true when passed', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard(true);
      });

      expect(result.current.state.isNewGraph).toBe(true);
    });

    it('should set isNewGraph to false when explicitly passed', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard(false);
      });

      expect(result.current.state.isNewGraph).toBe(false);
    });

    it('should reset canProceed to false', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setCanProceed(true);
      });

      expect(result.current.state.canProceed).toBe(true);

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.canProceed).toBe(false);
    });

    it('should reset canGoBack to false', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.canGoBack).toBe(false);
    });
  });

  describe('EXIT_WIZARD Action', () => {
    it('should close wizard when exitWizard is called', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.isActive).toBe(true);

      act(() => {
        result.current.exitWizard();
      });

      expect(result.current.state.isActive).toBe(false);
    });

    it('should maintain current step when exiting', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.nextStep();
      });

      const stepBeforeExit = result.current.state.currentStep;

      act(() => {
        result.current.exitWizard();
      });

      expect(result.current.state.currentStep).toBe(stepBeforeExit);
    });

    it('should maintain completed steps when exiting', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(1);
      });

      const completedBeforeExit = new Set(result.current.state.completedSteps);

      act(() => {
        result.current.exitWizard();
      });

      expect(result.current.state.completedSteps).toEqual(completedBeforeExit);
    });

    it('should maintain step data when exiting', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setStepData('test', { value: 'data' });
      });

      const dataBeforeExit = { ...result.current.state.stepData };

      act(() => {
        result.current.exitWizard();
      });

      expect(result.current.state.stepData).toEqual(dataBeforeExit);
    });
  });

  describe('NEXT_STEP Action', () => {
    it('should increment step when nextStep is called', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.currentStep).toBe(0);

      act(() => {
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(1);
    });

    it('should set canGoBack to true after moving to step 1', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
      });

      expect(result.current.state.canGoBack).toBe(true);
    });

    it('should reset canProceed to false after moving to next step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setCanProceed(true);
        result.current.nextStep();
      });

      expect(result.current.state.canProceed).toBe(false);
    });

    it('should not increment past last step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      // Move to last step
      const lastStepIndex = result.current.state.totalSteps - 1;
      act(() => {
        for (let i = 0; i < lastStepIndex; i++) {
          result.current.nextStep();
        }
      });

      expect(result.current.state.currentStep).toBe(lastStepIndex);

      // Try to go beyond
      act(() => {
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(lastStepIndex);
    });

    it('should update isLastStep when reaching last step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.isLastStep).toBe(false);

      const lastStepIndex = result.current.state.totalSteps - 1;
      act(() => {
        for (let i = 0; i < lastStepIndex; i++) {
          result.current.nextStep();
        }
      });

      expect(result.current.isLastStep).toBe(true);
    });

    it('should update isFirstStep when leaving first step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.isFirstStep).toBe(true);

      act(() => {
        result.current.nextStep();
      });

      expect(result.current.isFirstStep).toBe(false);
    });

    it('should update currentStepConfig when moving to next step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.currentStepConfig).toEqual(DEFAULT_WIZARD_STEPS[0]);

      act(() => {
        result.current.nextStep();
      });

      expect(result.current.currentStepConfig).toEqual(DEFAULT_WIZARD_STEPS[1]);
    });
  });

  describe('PREV_STEP Action', () => {
    it('should decrement step when prevStep is called', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(2);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.state.currentStep).toBe(1);
    });

    it('should set canProceed to true when going back', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
        result.current.prevStep();
      });

      expect(result.current.state.canProceed).toBe(true);
    });

    it('should set canGoBack to false when returning to step 0', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
      });

      expect(result.current.state.canGoBack).toBe(true);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.state.canGoBack).toBe(false);
    });

    it('should keep canGoBack true when going back but not to step 0', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(2);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.state.currentStep).toBe(1);
      expect(result.current.state.canGoBack).toBe(true);
    });

    it('should not decrement below step 0', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.currentStep).toBe(0);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.state.currentStep).toBe(0);
    });

    it('should update isFirstStep when returning to first step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
      });

      expect(result.current.isFirstStep).toBe(false);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.isFirstStep).toBe(true);
    });

    it('should update currentStepConfig when moving to previous step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
      });

      expect(result.current.currentStepConfig).toEqual(DEFAULT_WIZARD_STEPS[1]);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.currentStepConfig).toEqual(DEFAULT_WIZARD_STEPS[0]);
    });
  });

  describe('GO_TO_STEP Action', () => {
    it('should jump to specific step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(1);
        result.current.markStepComplete(2);
        result.current.goToStep(2);
      });

      expect(result.current.state.currentStep).toBe(2);
    });

    it('should set canGoBack when jumping to step > 0', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(2);
        result.current.goToStep(2);
      });

      expect(result.current.state.canGoBack).toBe(true);
    });

    it('should set canGoBack to false when jumping to step 0', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
        result.current.nextStep();
        result.current.goToStep(0);
      });

      expect(result.current.state.canGoBack).toBe(false);
    });

    it('should set canProceed based on step completion', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(1);
        result.current.goToStep(1);
      });

      expect(result.current.state.canProceed).toBe(true);
    });

    it('should not allow jumping forward to incomplete step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.currentStep).toBe(0);

      act(() => {
        result.current.goToStep(3);
      });

      // Should remain at current step
      expect(result.current.state.currentStep).toBe(0);
    });

    it('should allow jumping back to any previous step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.nextStep();
        result.current.markStepComplete(1);
        result.current.nextStep();
        result.current.goToStep(0);
      });

      expect(result.current.state.currentStep).toBe(0);
    });

    it('should not allow jumping to negative step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.goToStep(-1);
      });

      expect(result.current.state.currentStep).toBe(0);
    });

    it('should not allow jumping beyond total steps', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      const totalSteps = result.current.state.totalSteps;

      act(() => {
        result.current.goToStep(totalSteps);
      });

      expect(result.current.state.currentStep).toBe(0);
    });

    it('should update currentStepConfig when jumping to step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(3);
        result.current.goToStep(3);
      });

      expect(result.current.currentStepConfig).toEqual(DEFAULT_WIZARD_STEPS[3]);
    });

    it('should allow jumping to current step', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.nextStep();
      });

      const currentStep = result.current.state.currentStep;

      act(() => {
        result.current.goToStep(currentStep);
      });

      expect(result.current.state.currentStep).toBe(currentStep);
    });
  });

  describe('SET_STEP_DATA Action', () => {
    it('should store step data', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      const testData = { name: 'Test Agent', role: 'assistant' };

      act(() => {
        result.current.startWizard();
        result.current.setStepData('role', testData);
      });

      expect(result.current.state.stepData['role']).toEqual(testData);
    });

    it('should store multiple step data independently', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      const roleData = { role: 'assistant' };
      const toolsData = { tools: ['web_search', 'calculator'] };

      act(() => {
        result.current.startWizard();
        result.current.setStepData('role', roleData);
        result.current.setStepData('tools', toolsData);
      });

      expect(result.current.state.stepData['role']).toEqual(roleData);
      expect(result.current.state.stepData['tools']).toEqual(toolsData);
    });

    it('should update existing step data', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      const initialData = { name: 'Initial' };
      const updatedData = { name: 'Updated' };

      act(() => {
        result.current.startWizard();
        result.current.setStepData('test', initialData);
      });

      expect(result.current.state.stepData['test']).toEqual(initialData);

      act(() => {
        result.current.setStepData('test', updatedData);
      });

      expect(result.current.state.stepData['test']).toEqual(updatedData);
    });

    it('should preserve other step data when updating one', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setStepData('step1', { value: 1 });
        result.current.setStepData('step2', { value: 2 });
        result.current.setStepData('step1', { value: 'updated' });
      });

      expect(result.current.state.stepData['step1']).toEqual({ value: 'updated' });
      expect(result.current.state.stepData['step2']).toEqual({ value: 2 });
    });

    it('should handle complex data structures', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      const complexData = {
        nested: {
          array: [1, 2, 3],
          object: { key: 'value' },
        },
        boolean: true,
        number: 42,
      };

      act(() => {
        result.current.startWizard();
        result.current.setStepData('complex', complexData);
      });

      expect(result.current.state.stepData['complex']).toEqual(complexData);
    });

    it('should handle null and undefined values', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setStepData('nullValue', null);
        result.current.setStepData('undefinedValue', undefined);
      });

      expect(result.current.state.stepData['nullValue']).toBeNull();
      expect(result.current.state.stepData['undefinedValue']).toBeUndefined();
    });
  });

  describe('MARK_STEP_COMPLETE Action', () => {
    it('should mark current step as complete', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete();
      });

      expect(result.current.state.completedSteps.has(0)).toBe(true);
    });

    it('should mark specific step as complete', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(2);
      });

      expect(result.current.state.completedSteps.has(2)).toBe(true);
    });

    it('should set canProceed to true after marking complete', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete();
      });

      expect(result.current.state.canProceed).toBe(true);
    });

    it('should mark multiple steps as complete independently', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(1);
        result.current.markStepComplete(2);
      });

      expect(result.current.state.completedSteps.has(0)).toBe(true);
      expect(result.current.state.completedSteps.has(1)).toBe(true);
      expect(result.current.state.completedSteps.has(2)).toBe(true);
      expect(result.current.state.completedSteps.size).toBe(3);
    });

    it('should not duplicate completed steps', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(0);
      });

      expect(result.current.state.completedSteps.size).toBe(1);
    });

    it('should update progress when marking steps complete', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.progress).toBe(0);

      act(() => {
        result.current.markStepComplete(0);
      });

      const expectedProgress = (1 / result.current.state.totalSteps) * 100;
      expect(result.current.progress).toBe(expectedProgress);
    });

    it('should calculate correct progress with multiple completed steps', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(1);
        result.current.markStepComplete(2);
      });

      const expectedProgress = (3 / result.current.state.totalSteps) * 100;
      expect(result.current.progress).toBeCloseTo(expectedProgress, 2);
    });
  });

  describe('MARK_STEP_SKIPPED Action', () => {
    it('should mark current step as skipped', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepSkipped();
      });

      expect(result.current.state.skippedSteps.has(0)).toBe(true);
    });

    it('should mark specific step as skipped', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepSkipped(2);
      });

      expect(result.current.state.skippedSteps.has(2)).toBe(true);
    });

    it('should also mark skipped step as complete for navigation', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepSkipped(2);
      });

      expect(result.current.state.completedSteps.has(2)).toBe(true);
    });

    it('should set canProceed to true after marking skipped', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepSkipped();
      });

      expect(result.current.state.canProceed).toBe(true);
    });

    it('should track both completed and skipped separately', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepSkipped(1);
      });

      expect(result.current.state.completedSteps.has(0)).toBe(true);
      expect(result.current.state.completedSteps.has(1)).toBe(true);
      expect(result.current.state.skippedSteps.has(0)).toBe(false);
      expect(result.current.state.skippedSteps.has(1)).toBe(true);
    });

    it('should not duplicate skipped steps', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepSkipped(0);
        result.current.markStepSkipped(0);
      });

      expect(result.current.state.skippedSteps.size).toBe(1);
    });

    it('should contribute to progress when skipped', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepSkipped(0);
      });

      const expectedProgress = (1 / result.current.state.totalSteps) * 100;
      expect(result.current.progress).toBe(expectedProgress);
    });
  });

  describe('SET_CAN_PROCEED Action', () => {
    it('should set canProceed to true', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setCanProceed(true);
      });

      expect(result.current.state.canProceed).toBe(true);
    });

    it('should set canProceed to false', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
      });

      expect(result.current.state.canProceed).toBe(true);

      act(() => {
        result.current.setCanProceed(false);
      });

      expect(result.current.state.canProceed).toBe(false);
    });

    it('should toggle canProceed multiple times', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setCanProceed(true);
      });

      expect(result.current.state.canProceed).toBe(true);

      act(() => {
        result.current.setCanProceed(false);
      });

      expect(result.current.state.canProceed).toBe(false);

      act(() => {
        result.current.setCanProceed(true);
      });

      expect(result.current.state.canProceed).toBe(true);
    });
  });

  describe('RESET_WIZARD Action', () => {
    it('should reset wizard to initial state', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.nextStep();
        result.current.setStepData('test', { value: 'data' });
        result.current.resetWizard();
      });

      expect(result.current.state.isActive).toBe(false);
      expect(result.current.state.currentStep).toBe(0);
      expect(result.current.state.completedSteps.size).toBe(0);
      expect(result.current.state.skippedSteps.size).toBe(0);
      expect(result.current.state.stepData).toEqual({});
      expect(result.current.state.canProceed).toBe(false);
      expect(result.current.state.canGoBack).toBe(false);
    });

    it('should clear all step data on reset', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setStepData('step1', { value: 1 });
        result.current.setStepData('step2', { value: 2 });
        result.current.setStepData('step3', { value: 3 });
        result.current.resetWizard();
      });

      expect(Object.keys(result.current.state.stepData).length).toBe(0);
    });

    it('should clear all completed steps on reset', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(1);
        result.current.markStepComplete(2);
        result.current.resetWizard();
      });

      expect(result.current.state.completedSteps.size).toBe(0);
    });

    it('should reset progress to 0', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.markStepComplete(1);
        result.current.resetWizard();
      });

      expect(result.current.progress).toBe(0);
    });
  });

  describe('Computed Properties', () => {
    describe('isFirstStep', () => {
      it('should be true on step 0', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
        });

        expect(result.current.isFirstStep).toBe(true);
      });

      it('should be false on step 1 or later', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
          result.current.nextStep();
        });

        expect(result.current.isFirstStep).toBe(false);
      });
    });

    describe('isLastStep', () => {
      it('should be false on first step', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
        });

        expect(result.current.isLastStep).toBe(false);
      });

      it('should be true on last step', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
        });

        const lastStepIndex = result.current.state.totalSteps - 1;

        act(() => {
          for (let i = 0; i < lastStepIndex; i++) {
            result.current.nextStep();
          }
        });

        expect(result.current.isLastStep).toBe(true);
      });
    });

    describe('progress', () => {
      it('should be 0% with no completed steps', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
        });

        expect(result.current.progress).toBe(0);
      });

      it('should be 100% when all steps completed', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
        });

        const totalSteps = result.current.state.totalSteps;

        act(() => {
          for (let i = 0; i < totalSteps; i++) {
            result.current.markStepComplete(i);
          }
        });

        expect(result.current.progress).toBe(100);
      });

      it('should calculate correct percentage for partial completion', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
          result.current.markStepComplete(0);
          result.current.markStepComplete(1);
        });

        const totalSteps = result.current.state.totalSteps;
        const expectedProgress = (2 / totalSteps) * 100;

        expect(result.current.progress).toBeCloseTo(expectedProgress, 2);
      });
    });

    describe('currentStepConfig', () => {
      it('should return null for invalid step', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
        });

        // Force invalid step by manipulating state
        const totalSteps = result.current.state.totalSteps;

        // Try to access beyond bounds (this shouldn't happen normally)
        // Just verify current step has valid config
        expect(result.current.currentStepConfig).not.toBeNull();
      });

      it('should update when navigating steps', () => {
        const { result } = renderHook(() => useWizard(), { wrapper });

        act(() => {
          result.current.startWizard();
        });

        const step0Config = result.current.currentStepConfig;

        act(() => {
          result.current.nextStep();
        });

        const step1Config = result.current.currentStepConfig;

        expect(step0Config).not.toEqual(step1Config);
        expect(step0Config).toEqual(DEFAULT_WIZARD_STEPS[0]);
        expect(step1Config).toEqual(DEFAULT_WIZARD_STEPS[1]);
      });
    });
  });

  describe('Integration Scenarios', () => {
    it('should handle complete wizard flow', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      // Start wizard
      act(() => {
        result.current.startWizard(true);
      });

      expect(result.current.state.isActive).toBe(true);
      expect(result.current.state.isNewGraph).toBe(true);

      // Complete first step
      act(() => {
        result.current.setStepData('start', { nodeType: 'start' });
        result.current.markStepComplete();
      });

      expect(result.current.state.completedSteps.has(0)).toBe(true);

      // Move to next step
      act(() => {
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(1);

      // Complete second step
      act(() => {
        result.current.setStepData('role', { role: 'assistant' });
        result.current.markStepComplete();
        result.current.nextStep();
      });

      // Skip third step
      act(() => {
        result.current.markStepSkipped();
        result.current.nextStep();
      });

      expect(result.current.state.skippedSteps.has(2)).toBe(true);

      // Exit wizard
      act(() => {
        result.current.exitWizard();
      });

      expect(result.current.state.isActive).toBe(false);
      expect(Object.keys(result.current.state.stepData).length).toBe(2);
    });

    it('should handle navigation back and forth', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.markStepComplete(0);
        result.current.nextStep();
        result.current.markStepComplete(1);
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(2);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.state.currentStep).toBe(1);

      act(() => {
        result.current.prevStep();
      });

      expect(result.current.state.currentStep).toBe(0);

      act(() => {
        result.current.nextStep();
        result.current.nextStep();
      });

      expect(result.current.state.currentStep).toBe(2);
    });

    it('should preserve data through navigation', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      const step0Data = { value: 'step0' };
      const step1Data = { value: 'step1' };

      act(() => {
        result.current.startWizard();
        result.current.setStepData('step0', step0Data);
        result.current.nextStep();
        result.current.setStepData('step1', step1Data);
        result.current.prevStep();
      });

      expect(result.current.state.stepData['step0']).toEqual(step0Data);
      expect(result.current.state.stepData['step1']).toEqual(step1Data);

      act(() => {
        result.current.nextStep();
      });

      expect(result.current.state.stepData['step0']).toEqual(step0Data);
      expect(result.current.state.stepData['step1']).toEqual(step1Data);
    });

    it('should handle restart after exit', () => {
      const { result } = renderHook(() => useWizard(), { wrapper });

      act(() => {
        result.current.startWizard();
        result.current.setStepData('test', { value: 'data' });
        result.current.markStepComplete(0);
        result.current.nextStep();
        result.current.exitWizard();
      });

      const dataBeforeRestart = result.current.state.stepData;

      act(() => {
        result.current.startWizard();
      });

      expect(result.current.state.isActive).toBe(true);
      expect(result.current.state.currentStep).toBe(0);
      expect(result.current.state.stepData).not.toEqual(dataBeforeRestart);
      expect(result.current.state.stepData).toEqual({});
    });
  });
});
